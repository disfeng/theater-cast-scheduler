from __future__ import annotations

from dataclasses import dataclass
import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now

from app.models.entities import (
    Designation,
    DesignationVersion,
    EntitlementLedgerEntry,
    EntitlementItem,
    Wish,
    WishLifecycleEvent,
    WishVersion,
)
from app.models.enums import EntitlementEventType, EntitlementItemStatus
from app.schemas.performance_boards import DesignationCorrectionPatch, WishCorrectionPatch
from app.services.designations import _audit, _ledger, _validate
from app.services.entitlements import reverse_consumption


class CorrectionConflict(ValueError):
    pass


@dataclass(frozen=True)
class CorrectionPreview:
    release_item_id: int | None
    reserve_item_id: int | None
    reverse_ledger_entry_id: int | None
    requires_reversal: bool
    immutable_fields: tuple[str, ...]


def _locked_designation(db: Session, designation_id: int) -> Designation:
    row = db.scalar(
        select(Designation)
        .where(Designation.id == designation_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise CorrectionConflict("designation_not_found")
    return row


def _validate_patch(row: Designation, patch: DesignationCorrectionPatch) -> None:
    if not patch.reason.strip():
        raise CorrectionConflict("correction_reason_required")
    if row.lifecycle_status == "fulfilled" and (
        (patch.actor_id is not None and patch.actor_id != row.actor_id)
        or (patch.role_id is not None and patch.role_id != row.role_id)
    ):
        raise CorrectionConflict("completed_performance_facts_immutable")


def preview_designation_correction(
    db: Session, designation_id: int, patch: DesignationCorrectionPatch
) -> CorrectionPreview:
    row = db.get(Designation, designation_id)
    if row is None:
        raise CorrectionConflict("designation_not_found")
    _validate_patch(row, patch)
    material_change = any(
        (
            patch.actor_id is not None and patch.actor_id != row.actor_id,
            patch.role_id is not None and patch.role_id != row.role_id,
            patch.usage_type is not None and patch.usage_type != row.usage_type,
            patch.owner_player_id is not None and patch.owner_player_id != row.owner_player_id,
            patch.entitlement_item_id is not None
            and patch.entitlement_item_id != row.entitlement_item_id,
        )
    )
    return CorrectionPreview(
        release_item_id=(
            row.entitlement_item_id
            if row.lifecycle_status == "predesignated" and material_change
            else None
        ),
        reserve_item_id=patch.entitlement_item_id,
        reverse_ledger_entry_id=None,
        requires_reversal=row.lifecycle_status == "effective" and material_change,
        immutable_fields=("actor_id", "role_id") if row.lifecycle_status == "fulfilled" else (),
    )


def _append_version(
    db: Session,
    row: Designation,
    patch: DesignationCorrectionPatch,
    operator_user_id: int,
) -> DesignationVersion:
    latest = (
        db.scalar(
            select(func.max(DesignationVersion.version_number)).where(
                DesignationVersion.designation_id == row.id
            )
        )
        or 0
    )
    if latest == 0:
        baseline = DesignationVersion(
            designation_id=row.id,
            version_number=1,
            player_name=row.player_name,
            actor_id=row.actor_id,
            role_id=row.role_id,
            usage_type=row.usage_type,
            owner_player_id=row.owner_player_id,
            entitlement_item_id=row.entitlement_item_id,
            created_by=operator_user_id,
        )
        db.add(baseline)
        db.flush()
        latest = 1
    version = DesignationVersion(
        designation_id=row.id,
        version_number=latest + 1,
        player_name=patch.player_name or row.player_name,
        actor_id=patch.actor_id or row.actor_id,
        role_id=patch.role_id or row.role_id,
        usage_type=patch.usage_type if patch.usage_type is not None else row.usage_type,
        owner_player_id=(
            patch.owner_player_id if patch.owner_player_id is not None else row.owner_player_id
        ),
        entitlement_item_id=(
            patch.entitlement_item_id
            if patch.entitlement_item_id is not None
            else row.entitlement_item_id
        ),
        note=patch.note,
        correction_reason=patch.reason,
        created_by=operator_user_id,
    )
    db.add(version)
    db.flush()
    return version


def correct_designation(
    db: Session,
    designation_id: int,
    patch: DesignationCorrectionPatch,
    operator_user_id: int,
) -> Designation:
    row = _locked_designation(db, designation_id)
    _validate_patch(row, patch)
    if not patch.confirmed:
        raise CorrectionConflict("correction_confirmation_required")
    if row.version != patch.expected_version:
        raise CorrectionConflict("correction_version_conflict")
    material_change = any(
        (
            patch.actor_id is not None and patch.actor_id != row.actor_id,
            patch.role_id is not None and patch.role_id != row.role_id,
            patch.usage_type is not None and patch.usage_type != row.usage_type,
            patch.owner_player_id is not None and patch.owner_player_id != row.owner_player_id,
            patch.entitlement_item_id is not None
            and patch.entitlement_item_id != row.entitlement_item_id,
        )
    )
    if row.lifecycle_status == "fulfilled" and material_change:
        raise CorrectionConflict("completed_performance_facts_immutable")

    old_status = row.lifecycle_status
    old_item = db.get(EntitlementItem, row.entitlement_item_id) if row.entitlement_item_id else None
    selected_item_id = (
        patch.entitlement_item_id
        if patch.entitlement_item_id is not None
        else row.entitlement_item_id
    )
    new_item = db.get(EntitlementItem, selected_item_id) if selected_item_id else None
    should_rebind_item = old_status not in {"effective", "fulfilled"} or material_change
    if patch.entitlement_item_id is not None and new_item is None:
        raise CorrectionConflict("entitlement_item_not_found")
    if new_item is not None and (old_item is None or new_item.id != old_item.id):
        _validate(db, row, new_item)

    if row.lifecycle_status == "effective" and material_change and old_item is not None:
        consumed = db.scalar(
            select(EntitlementLedgerEntry)
            .where(
                EntitlementLedgerEntry.designation_id == row.id,
                EntitlementLedgerEntry.event_type == EntitlementEventType.CONSUMED,
            )
            .order_by(EntitlementLedgerEntry.id.desc())
            .with_for_update()
        )
        if consumed is None:
            raise CorrectionConflict("correction_consumption_ledger_not_found")
        reverse_consumption(
            db,
            consumed.id,
            row.id,
            patch.reason,
            operator_user_id,
            f"{patch.idempotency_key}:reverse",
            commit=False,
        )

    version = _append_version(db, row, patch, operator_user_id)
    if (
        should_rebind_item
        and old_item is not None
        and old_item.status == EntitlementItemStatus.RESERVED
    ):
        released_status = (
            EntitlementItemStatus.EXPIRED
            if old_item.expires_at <= utc_now()
            else EntitlementItemStatus.AVAILABLE
        )
        before = old_item.status
        old_item.status = released_status
        old_item.current_designation_id = None
        _ledger(db, old_item, row, operator_user_id, before, released_status, patch.reason)
    if should_rebind_item and new_item is not None:
        if new_item.status != EntitlementItemStatus.AVAILABLE:
            raise CorrectionConflict("entitlement_not_available")
        before = new_item.status
        new_item.status = EntitlementItemStatus.RESERVED
        new_item.current_designation_id = row.id
        _ledger(db, new_item, row, operator_user_id, before, new_item.status, patch.reason)

    row.player_name = version.player_name
    row.actor_id = version.actor_id
    row.role_id = version.role_id
    row.usage_type = version.usage_type
    row.owner_player_id = version.owner_player_id
    row.entitlement_item_id = version.entitlement_item_id
    row.current_version_id = version.id
    if old_status == "fulfilled":
        row.lifecycle_status = "fulfilled"
    elif old_status == "effective" and not material_change:
        row.lifecycle_status = "effective"
    else:
        row.lifecycle_status = "predesignated" if new_item is not None else "draft"
    row.failure_reason = None
    row.version += 1
    _audit(
        db,
        row,
        "correct",
        patch.idempotency_key,
        operator_user_id,
        old_status,
        patch.model_dump(mode="json"),
        new_item,
        note=patch.reason,
    )
    db.flush()
    return row


def preview_wish_correction(
    db: Session, wish_id: int, patch: WishCorrectionPatch
) -> CorrectionPreview:
    row = db.get(Wish, wish_id)
    if row is None:
        raise CorrectionConflict("wish_not_found")
    if row.status == "fulfilled" and (
        (patch.actor_id is not None and patch.actor_id != row.actor_id)
        or (patch.role_id is not None and patch.role_id != row.role_id)
    ):
        raise CorrectionConflict("completed_performance_facts_immutable")
    return CorrectionPreview(
        release_item_id=None,
        reserve_item_id=None,
        reverse_ledger_entry_id=None,
        requires_reversal=False,
        immutable_fields=("actor_id", "role_id") if row.status == "fulfilled" else (),
    )


def correct_wish(
    db: Session, wish_id: int, patch: WishCorrectionPatch, operator_user_id: int
) -> Wish:
    row = db.scalar(
        select(Wish)
        .where(Wish.id == wish_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise CorrectionConflict("wish_not_found")
    preview_wish_correction(db, wish_id, patch)
    if not patch.confirmed:
        raise CorrectionConflict("correction_confirmation_required")
    if row.version != patch.expected_version:
        raise CorrectionConflict("correction_version_conflict")
    latest = (
        db.scalar(select(func.max(WishVersion.version_number)).where(WishVersion.wish_id == row.id))
        or 0
    )
    if latest == 0:
        db.add(
            WishVersion(
                wish_id=row.id,
                version_number=1,
                player_name=row.player_name,
                actor_id=row.actor_id,
                role_id=row.role_id,
                note=row.note,
                created_by=operator_user_id,
            )
        )
        db.flush()
        latest = 1
    version = WishVersion(
        wish_id=row.id,
        version_number=latest + 1,
        player_name=patch.player_name or row.player_name,
        actor_id=patch.actor_id or row.actor_id,
        role_id=patch.role_id or row.role_id,
        note=patch.note if patch.note is not None else row.note,
        correction_reason=patch.reason,
        created_by=operator_user_id,
    )
    db.add(version)
    db.flush()
    old_status = row.status
    actor_or_role_changed = version.actor_id != row.actor_id or version.role_id != row.role_id
    row.player_name = version.player_name
    row.actor_id = version.actor_id
    row.role_id = version.role_id
    row.note = version.note
    row.current_version_id = version.id
    if old_status == "effective" and actor_or_role_changed:
        row.status = "accepted"
        row.failure_reason = None
    row.version += 1
    db.add(
        WishLifecycleEvent(
            wish_id=row.id,
            operator_user_id=operator_user_id,
            action="correct",
            idempotency_key=patch.idempotency_key,
            request_hash=hashlib.sha256(patch.model_dump_json().encode()).hexdigest(),
            result_snapshot={
                "id": row.id,
                "version": row.version,
                "status": row.status,
                "current_version_id": version.id,
            },
            from_status=old_status,
            to_status=row.status,
            note=patch.reason,
        )
    )
    db.flush()
    return row
