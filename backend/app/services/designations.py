from __future__ import annotations
from copy import copy
import hashlib
import json
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from app.core.time import utc_now
from app.models.entities import (
    ActorRoleCapability,
    Designation,
    DesignationLifecycleEvent,
    EntitlementItem,
    EntitlementLedgerEntry,
    Performance,
    PerformancePlayer,
    PlayerProfile,
    Role,
    User,
)
from app.models.enums import (
    EntitlementEventType,
    EntitlementItemCategory,
    EntitlementItemStatus,
    PlayerStatus,
)
from app.services.entitlement_binding import (
    EntitlementBindingError,
    validate_designation_binding,
)
from app.services.designation_workspace import project_designation_conflicts


class DesignationConflict(ValueError):
    pass


def _designation(db, designation_id):
    row = db.scalar(
        select(Designation)
        .where(Designation.id == designation_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise DesignationConflict("designation_not_found")
    return row


def _item(db, item_id):
    row = db.scalar(
        select(EntitlementItem)
        .where(EntitlementItem.id == item_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise DesignationConflict("entitlement_item_not_found")
    return row


def _operator(db, operator_id):
    if db.get(User, operator_id) is None:
        raise DesignationConflict("operator_not_found")


def _replay(db, row, action, key):
    return db.scalar(
        select(DesignationLifecycleEvent).where(
            DesignationLifecycleEvent.designation_id == row.id,
            DesignationLifecycleEvent.action == action,
            DesignationLifecycleEvent.idempotency_key == key,
        )
    )


def _fingerprint(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def _guard(db, row, action, expected_version, key, operator_id, payload):
    _operator(db, operator_id)
    event = _replay(db, row, action, key) if key else None
    if event:
        if event.operator_user_id != operator_id or event.request_hash != _fingerprint(payload):
            raise DesignationConflict("idempotency_conflict")
        replay = copy(row)
        replay._idempotency_response_snapshot = event.result_snapshot
        for field, value in event.result_snapshot.get("designation", event.result_snapshot).items():
            if hasattr(replay, field):
                setattr(replay, field, value)
        return replay
    if expected_version is not None and row.version != expected_version:
        raise DesignationConflict("designation_version_conflict")
    return None


def _audit(db, row, action, key, operator, old, payload, item=None, conflict=None, note=None):
    if not key:
        key = f"internal-{action}-{row.id}-{row.version}"
    db.add(
        DesignationLifecycleEvent(
            designation_id=row.id,
            operator_user_id=operator,
            action=action,
            idempotency_key=key,
            from_status=old,
            to_status=row.lifecycle_status,
            request_hash=_fingerprint(payload),
            result_snapshot={
                "lifecycle_status": row.lifecycle_status,
                "failure_reason": row.failure_reason,
                "version": row.version,
                "entitlement_item_id": row.entitlement_item_id,
                "replaced_designation_id": row.replaced_designation_id,
            },
            entitlement_item_id=item.id if item else None,
            conflict_designation_id=conflict.id if conflict else None,
            note=note,
        )
    )


def _validate(db, row, item, allow_own_reserved=False):
    if row.performance_id is None or row.beneficiary_performance_player_id is None:
        raise DesignationConflict("beneficiary_not_in_performance")
    if row.target_performance_id is not None and row.target_performance_id != row.performance_id:
        raise DesignationConflict("designation_performance_scope_mismatch")
    performance, role = db.get(Performance, row.performance_id), db.get(Role, row.role_id)
    if performance is None or role is None or role.theater_id != performance.theater_id:
        raise DesignationConflict("designation_role_outside_performance_theater")
    beneficiary = db.scalar(
        select(PerformancePlayer).where(
            PerformancePlayer.id == row.beneficiary_performance_player_id,
            PerformancePlayer.performance_id == row.performance_id,
            PerformancePlayer.is_active.is_(True),
        )
    )
    if beneficiary is None or beneficiary.player_profile_id is None:
        raise DesignationConflict("beneficiary_not_in_performance")
    profile = db.get(PlayerProfile, beneficiary.player_profile_id)
    if profile is None or profile.status != PlayerStatus.ACTIVE:
        raise DesignationConflict("player_not_confirmed")
    if not db.scalar(
        select(ActorRoleCapability.id).where(
            ActorRoleCapability.actor_id == row.actor_id, ActorRoleCapability.role_id == row.role_id
        )
    ):
        raise DesignationConflict("actor_role_capability_missing")
    if item.owner_id != row.owner_player_id:
        raise DesignationConflict("entitlement_owner_mismatch")
    if (
        item.theater_id != performance.theater_id
        or item.item_type.theater_id != performance.theater_id
    ):
        raise DesignationConflict("entitlement_theater_mismatch")
    if (
        item.item_type.category != EntitlementItemCategory.DESIGNATION
        or item.item_type.designation_type != row.designation_type
    ):
        raise DesignationConflict("entitlement_type_mismatch")
    try:
        validate_designation_binding(item, beneficiary.player_profile_id, row.actor_id)
    except EntitlementBindingError as exc:
        raise DesignationConflict(str(exc)) from exc
    if item.status == EntitlementItemStatus.RESERVED:
        if allow_own_reserved and item.current_designation_id == row.id:
            return beneficiary
        raise DesignationConflict("entitlement_already_reserved")
    if item.status != EntitlementItemStatus.AVAILABLE:
        raise DesignationConflict("entitlement_not_available")
    if item.expires_at <= utc_now():
        raise DesignationConflict("entitlement_expired")
    return beneficiary


def _occupied(db, row):
    return db.scalar(
        select(Designation)
        .where(
            Designation.id != row.id,
            Designation.performance_id == row.performance_id,
            Designation.lifecycle_status == "predesignated",
            or_(Designation.role_id == row.role_id, Designation.actor_id == row.actor_id),
        )
        .order_by(Designation.id)
        .with_for_update()
    )


def _ledger(db, item, row, operator, old, new, reason=None):
    db.add(
        EntitlementLedgerEntry(
            item_id=item.id,
            event_type=EntitlementEventType.RELEASED
            if old == EntitlementItemStatus.RESERVED
            else EntitlementEventType.RESERVED,
            from_status=old,
            to_status=new,
            performance_id=row.performance_id,
            designation_id=row.id,
            reason=reason,
            operator_user_id=operator,
        )
    )


def _reserve_or_pending(db, row, item, operator, action, key, payload):
    old = row.lifecycle_status
    occupied = _occupied(db, row)
    hard_conflicts = [
        conflict
        for conflict in project_designation_conflicts(db, row)
        if conflict.severity == "hard" and conflict.code != "ACTOR_ALREADY_IN_PERFORMANCE"
    ]
    if hard_conflicts:
        codes = ",".join(conflict.code for conflict in hard_conflicts)
        raise DesignationConflict(f"designation_hard_conflict:{codes}")
    row.entitlement_item_id = item.id
    if occupied:
        occupied_item = _item(db, occupied.entitlement_item_id)
        comparison = (
            "higher"
            if item.item_type.priority > occupied_item.item_type.priority
            else "lower"
            if item.item_type.priority < occupied_item.item_type.priority
            else "equal"
        )
        row.lifecycle_status = "pending_conflict" if comparison != "equal" else "manual_review"
        row.failure_reason = f"designation_priority_{comparison}"
        row.version += 1
        _audit(db, row, action, key, operator, old, payload, item, occupied, comparison)
        db.flush()
        return row
    item.status = EntitlementItemStatus.RESERVED
    item.current_designation_id = row.id
    row.lifecycle_status = "predesignated"
    row.failure_reason = None
    row.version += 1
    _ledger(db, item, row, operator, EntitlementItemStatus.AVAILABLE, item.status)
    _audit(db, row, action, key, operator, old, payload, item)
    db.flush()
    return row


def verify_self_designation(
    db: Session,
    designation_id: int,
    item_id: int,
    operator_user_id: int,
    *,
    expected_version=None,
    idempotency_key=None,
):
    row = _designation(db, designation_id)
    payload = {"item_id": item_id, "expected_version": expected_version}
    replay = _guard(
        db, row, "verify_self", expected_version, idempotency_key, operator_user_id, payload
    )
    if replay:
        return replay
    item = _item(db, item_id)
    beneficiary = _validate(db, row, item)
    if row.usage_type not in (None, "self") or row.owner_player_id != beneficiary.player_profile_id:
        raise DesignationConflict("self_owner_beneficiary_mismatch")
    row.usage_type = "self"
    row.verification_status = "not_required"
    row.verified_by = operator_user_id
    row.verified_at = utc_now()
    return _reserve_or_pending(
        db, row, item, operator_user_id, "verify_self", idempotency_key, payload
    )


def verify_proxy_designation(
    db: Session,
    designation_id: int,
    owner_player_id: int,
    item_id: int,
    note: str,
    operator_user_id: int,
    *,
    expected_version=None,
    idempotency_key=None,
):
    row = _designation(db, designation_id)
    payload = {
        "owner_player_id": owner_player_id,
        "item_id": item_id,
        "note": note.strip(),
        "expected_version": expected_version,
    }
    replay = _guard(
        db, row, "verify_proxy", expected_version, idempotency_key, operator_user_id, payload
    )
    if replay:
        return replay
    if not note.strip():
        raise DesignationConflict("proxy_verification_note_required")
    row.owner_player_id = owner_player_id
    item = _item(db, item_id)
    _validate(db, row, item)
    row.usage_type = "proxy"
    row.verification_status = "verified"
    row.verified_by = operator_user_id
    row.verified_at = utc_now()
    row.verification_note = note.strip()
    return _reserve_or_pending(
        db, row, item, operator_user_id, "verify_proxy", idempotency_key, payload
    )


def activate_predesignation(
    db: Session,
    designation_id: int,
    operator_user_id: int,
    *,
    expected_version=None,
    idempotency_key=None,
):
    row = _designation(db, designation_id)
    payload = {"expected_version": expected_version}
    replay = _guard(
        db, row, "activate", expected_version, idempotency_key, operator_user_id, payload
    )
    if replay:
        return replay
    if row.usage_type == "proxy" and row.verification_status != "verified":
        raise DesignationConflict("proxy_verification_required")
    if row.entitlement_item_id is None:
        raise DesignationConflict("entitlement_item_required")
    item = _item(db, row.entitlement_item_id)
    _validate(db, row, item, allow_own_reserved=True)
    if item.status == EntitlementItemStatus.RESERVED and item.current_designation_id == row.id:
        old = row.lifecycle_status
        _audit(db, row, "activate", idempotency_key, operator_user_id, old, payload, item)
        db.flush()
        return row
    return _reserve_or_pending(
        db, row, item, operator_user_id, "activate", idempotency_key, payload
    )


def replace_predesignation(
    db: Session,
    incoming_id: int,
    replaced_id: int,
    expected_versions: dict[str, int],
    operator_user_id: int,
    *,
    idempotency_key=None,
):
    rows = {
        r.id: r
        for r in db.scalars(
            select(Designation)
            .where(Designation.id.in_([incoming_id, replaced_id]))
            .order_by(Designation.id)
            .with_for_update()
        ).all()
    }
    if len(rows) != 2:
        raise DesignationConflict("designation_not_found")
    incoming, replaced = rows[incoming_id], rows[replaced_id]
    payload = {"replaced_id": replaced_id, "expected_versions": expected_versions}
    replay = _guard(
        db,
        incoming,
        "replace",
        expected_versions.get("incoming"),
        idempotency_key,
        operator_user_id,
        payload,
    )
    if replay:
        return replay
    if replaced.version != expected_versions.get("replaced"):
        raise DesignationConflict("designation_version_conflict")
    if (
        incoming.entitlement_item_id is None
        or replaced.entitlement_item_id is None
        or replaced.lifecycle_status != "predesignated"
    ):
        raise DesignationConflict("designation_replacement_invalid_state")
    items = {
        i.id: i
        for i in db.scalars(
            select(EntitlementItem)
            .where(
                EntitlementItem.id.in_([incoming.entitlement_item_id, replaced.entitlement_item_id])
            )
            .order_by(EntitlementItem.id)
            .with_for_update()
        ).all()
    }
    new, old = items[incoming.entitlement_item_id], items[replaced.entitlement_item_id]
    if new.item_type.priority <= old.item_type.priority:
        raise DesignationConflict("designation_priority_conflict")
    _validate(db, incoming, new)
    old_status = old.status
    old.status = (
        EntitlementItemStatus.EXPIRED
        if old.expires_at <= utc_now()
        else EntitlementItemStatus.AVAILABLE
    )
    old.current_designation_id = None
    _ledger(
        db, old, replaced, operator_user_id, old_status, old.status, "replaced_by_higher_priority"
    )
    replaced_old = replaced.lifecycle_status
    replaced.lifecycle_status = "replaced"
    replaced.failure_reason = "replaced_by_higher_priority"
    replaced.version += 1
    _audit(
        db,
        replaced,
        "replaced",
        f"{idempotency_key}:occupied",
        operator_user_id,
        replaced_old,
        payload,
        old,
        incoming,
    )
    incoming_old = incoming.lifecycle_status
    new.status = EntitlementItemStatus.RESERVED
    new.current_designation_id = incoming.id
    incoming.lifecycle_status = "predesignated"
    incoming.failure_reason = None
    incoming.replaced_designation_id = replaced.id
    incoming.version += 1
    _ledger(db, new, incoming, operator_user_id, EntitlementItemStatus.AVAILABLE, new.status)
    _audit(
        db,
        incoming,
        "replace",
        idempotency_key,
        operator_user_id,
        incoming_old,
        payload,
        new,
        replaced,
    )
    db.flush()
    return incoming


def resolve_equal_priority(
    db: Session,
    incoming_id: int,
    occupied_id: int,
    decision: str,
    expected_versions: dict[str, int],
    operator_user_id: int,
    *,
    idempotency_key: str,
):
    if incoming_id == occupied_id:
        raise DesignationConflict("designation_manual_choice_same_record")
    rows = {
        r.id: r
        for r in db.scalars(
            select(Designation)
            .where(Designation.id.in_([incoming_id, occupied_id]))
            .order_by(Designation.id)
            .with_for_update()
        ).all()
    }
    if len(rows) != 2:
        raise DesignationConflict("designation_not_found")
    incoming, occupied = rows[incoming_id], rows[occupied_id]
    payload = {
        "occupied_id": occupied_id,
        "decision": decision,
        "expected_versions": expected_versions,
    }
    replay = _guard(
        db,
        incoming,
        "resolve_equal",
        expected_versions.get("incoming"),
        idempotency_key,
        operator_user_id,
        payload,
    )
    if replay:
        return replay
    if occupied.version != expected_versions.get("occupied"):
        raise DesignationConflict("designation_version_conflict")
    if incoming.lifecycle_status != "manual_review" or occupied.lifecycle_status != "predesignated":
        raise DesignationConflict("designation_manual_choice_invalid_state")
    if incoming.performance_id != occupied.performance_id or not (
        incoming.role_id == occupied.role_id or incoming.actor_id == occupied.actor_id
    ):
        raise DesignationConflict("designation_manual_choice_unrelated")
    new, old = _item(db, incoming.entitlement_item_id), _item(db, occupied.entitlement_item_id)
    if new.item_type.priority != old.item_type.priority:
        raise DesignationConflict("designation_not_equal_priority")
    _validate(db, incoming, new)
    if old.status != EntitlementItemStatus.RESERVED or old.current_designation_id != occupied.id:
        raise DesignationConflict("designation_occupied_item_invariant")
    _validate(db, occupied, old, allow_own_reserved=True)
    before = incoming.lifecycle_status
    if decision == "keep_occupied":
        incoming.lifecycle_status = "pending_conflict"
        incoming.failure_reason = "manual_choice_kept_occupied"
        incoming.version += 1
        _audit(
            db,
            incoming,
            "resolve_equal",
            idempotency_key,
            operator_user_id,
            before,
            payload,
            new,
            occupied,
            decision,
        )
        db.flush()
        return incoming
    if decision != "choose_incoming":
        raise DesignationConflict("designation_manual_decision_invalid")
    old_state = old.status
    old.status = (
        EntitlementItemStatus.EXPIRED
        if old.expires_at <= utc_now()
        else EntitlementItemStatus.AVAILABLE
    )
    old.current_designation_id = None
    _ledger(
        db, old, occupied, operator_user_id, old_state, old.status, "manual_equal_priority_choice"
    )
    occupied.lifecycle_status = "replaced"
    occupied.failure_reason = "manual_equal_priority_choice"
    occupied.version += 1
    new.status = EntitlementItemStatus.RESERVED
    new.current_designation_id = incoming.id
    incoming.lifecycle_status = "predesignated"
    incoming.failure_reason = None
    incoming.replaced_designation_id = occupied.id
    incoming.version += 1
    _ledger(db, new, incoming, operator_user_id, EntitlementItemStatus.AVAILABLE, new.status)
    _audit(
        db,
        incoming,
        "resolve_equal",
        idempotency_key,
        operator_user_id,
        before,
        payload,
        new,
        occupied,
        decision,
    )
    db.flush()
    return incoming


def cancel_designation(
    db: Session,
    designation_id: int,
    reason: str,
    operator_user_id: int,
    *,
    expected_version=None,
    idempotency_key=None,
):
    reason = reason.strip()
    if not reason:
        raise DesignationConflict("designation_cancel_reason_required")
    row = _designation(db, designation_id)
    payload = {"reason": reason, "expected_version": expected_version}
    replay = _guard(db, row, "cancel", expected_version, idempotency_key, operator_user_id, payload)
    if replay:
        return replay
    if row.lifecycle_status in ("fulfilled", "replaced"):
        raise DesignationConflict("designation_cannot_cancel")
    old = row.lifecycle_status
    item = _item(db, row.entitlement_item_id) if row.entitlement_item_id else None
    if (
        item
        and item.status == EntitlementItemStatus.RESERVED
        and item.current_designation_id == row.id
    ):
        before = item.status
        item.status = (
            EntitlementItemStatus.EXPIRED
            if item.expires_at <= utc_now()
            else EntitlementItemStatus.AVAILABLE
        )
        item.current_designation_id = None
        _ledger(db, item, row, operator_user_id, before, item.status, reason)
    row.lifecycle_status = "cancelled"
    row.failure_reason = reason
    row.version += 1
    _audit(db, row, "cancel", idempotency_key, operator_user_id, old, payload, item, note=reason)
    db.flush()
    return row
