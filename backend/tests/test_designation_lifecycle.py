from datetime import date, datetime, time, timedelta

import pytest

from app.models.entities import (
    Actor,
    ActorRoleCapability,
    Designation,
    EntitlementItem,
    EntitlementItemType,
    Performance,
    PerformanceBoard,
    PerformanceBoardRevision,
    PerformancePlayer,
    PlayerProfile,
    Role,
    Theater,
    TheaterSlot,
    User,
    DesignationLifecycleEvent,
)
from app.models.enums import (
    DesignationType,
    EntitlementItemCategory,
    EntitlementItemStatus,
    PlayerStatus,
    UserRole,
)
from app.services.designations import (
    DesignationConflict,
    activate_predesignation,
    cancel_designation,
    replace_predesignation,
    resolve_equal_priority,
    verify_proxy_designation,
    verify_self_designation,
)


def _world(db):
    theater = Theater(name="T")
    db.add(theater)
    db.flush()
    slot = TheaterSlot(theater_id=theater.id, name="晚", start_time=time(19), sort_order=1)
    role = Role(theater_id=theater.id, name="R")
    actor = Actor(display_name="A")
    owner = PlayerProfile(display_name="Owner", normalized_name="owner", status=PlayerStatus.ACTIVE)
    beneficiary = PlayerProfile(
        display_name="Guest", normalized_name="guest", status=PlayerStatus.ACTIVE
    )
    operator = User(email="admin@test", password_hash="x", role=UserRole.ADMIN)
    db.add_all([slot, role, actor, owner, beneficiary, operator])
    db.flush()
    db.add(ActorRoleCapability(actor_id=actor.id, role_id=role.id))
    perf = Performance(
        theater_id=theater.id,
        theater_slot_id=slot.id,
        performance_date=date.today(),
        slot_name_snapshot="晚",
        start_time_snapshot=time(19),
    )
    db.add(perf)
    db.flush()
    board = PerformanceBoard(performance_id=perf.id)
    db.add(board)
    db.flush()
    rev = PerformanceBoardRevision(board_id=board.id, revision_number=1, raw_text="x")
    db.add(rev)
    db.flush()
    pp = PerformancePlayer(
        performance_id=perf.id,
        player_profile_id=beneficiary.id,
        player_name_snapshot="Guest",
        player_character_name="G",
        paired_role_name="R",
        source_board_id=board.id,
        source_revision_id=rev.id,
    )
    db.add(pp)
    db.flush()
    types = []
    for code, priority, binding in (
        ("universal", 300, DesignationType.UNIVERSAL),
        ("top_three", 200, DesignationType.TOP_THREE),
        ("paired", 100, DesignationType.PAIRED),
    ):
        typ = EntitlementItemType(
            theater_id=theater.id,
            code=code,
            display_name=code,
            category=EntitlementItemCategory.DESIGNATION,
            designation_type=binding,
            priority=priority,
            default_validity_months=3,
        )
        db.add(typ)
        db.flush()
        types.append(typ)
    db.commit()
    return perf, pp, owner, beneficiary, actor, role, operator, types


def _item(db, owner, typ, serial, days=30, bound_actor=None):
    item = EntitlementItem(
        theater_id=typ.theater_id,
        serial_number=serial,
        owner_id=owner.id,
        item_type_id=typ.id,
        source_month=date.today().replace(day=1),
        source_label="test",
        granted_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=days),
        status=EntitlementItemStatus.AVAILABLE,
        bound_actor_id=bound_actor.id if bound_actor is not None else None,
    )
    db.add(item)
    db.commit()
    return item


def test_custom_designation_item_code_uses_binding_and_theater_scope(db_session):
    perf, pp, _, beneficiary, actor, role, op, types = _world(db_session)
    custom = EntitlementItemType(
        theater_id=perf.theater_id,
        code="summer_vip_choice",
        display_name="夏季万能指定",
        category=EntitlementItemCategory.DESIGNATION,
        designation_type=DesignationType.UNIVERSAL,
        priority=350,
        default_validity_days=90,
    )
    db_session.add(custom)
    db_session.commit()
    item = _item(db_session, beneficiary, custom, "CUSTOM")
    row = _designation(db_session, perf, pp, beneficiary, actor, role, types[0])

    result = verify_self_designation(db_session, row.id, item.id, op.id)

    assert result.lifecycle_status == "predesignated"

    other = Theater(name="Other custom item theater")
    db_session.add(other)
    db_session.flush()
    custom.theater_id = other.id
    item.theater_id = other.id
    item.status = EntitlementItemStatus.AVAILABLE
    item.current_designation_id = None
    row.lifecycle_status = "draft"
    row.entitlement_item_id = None
    db_session.commit()
    with pytest.raises(DesignationConflict, match="entitlement_theater_mismatch"):
        verify_self_designation(db_session, row.id, item.id, op.id)


def _designation(db, perf, pp, owner, actor, role, kind, usage="self"):
    row = Designation(
        designation_type=DesignationType(kind.code),
        player_name=pp.player_name_snapshot,
        role_id=role.id,
        actor_id=actor.id,
        target_performance_id=perf.id,
        performance_id=perf.id,
        beneficiary_performance_player_id=pp.id,
        owner_player_id=owner.id,
        submitted_at=datetime.utcnow(),
        usage_type=usage,
        verification_status="not_required" if usage == "self" else "pending",
        lifecycle_status="draft" if usage == "self" else "pending_verification",
    )
    db.add(row)
    db.commit()
    return row


def test_self_requires_owner_beneficiary_and_confirmed_performance_player(db_session):
    perf, pp, owner, beneficiary, actor, role, op, types = _world(db_session)
    item = _item(db_session, owner, types[0], "U-1")
    designation = _designation(db_session, perf, pp, owner, actor, role, types[0])
    with pytest.raises(DesignationConflict, match="self_owner_beneficiary_mismatch"):
        verify_self_designation(db_session, designation.id, item.id, op.id)
    designation.owner_player_id = beneficiary.id
    item.owner_id = beneficiary.id
    pp.is_active = False
    db_session.commit()
    with pytest.raises(DesignationConflict, match="beneficiary_not_in_performance"):
        verify_self_designation(db_session, designation.id, item.id, op.id)


@pytest.mark.parametrize("index", [0, 1, 2])
def test_all_item_types_use_same_capability_rule_and_reserve_exact_item(db_session, index):
    perf, pp, owner, beneficiary, actor, role, op, types = _world(db_session)
    item = _item(
        db_session,
        beneficiary,
        types[index],
        f"I-{index}",
        bound_actor=actor if index == 1 else None,
    )
    designation = _designation(db_session, perf, pp, beneficiary, actor, role, types[index])
    result = verify_self_designation(db_session, designation.id, item.id, op.id)
    assert result.lifecycle_status == "predesignated"
    assert item.status == EntitlementItemStatus.RESERVED
    assert item.current_designation_id == designation.id
    assert item.ledger_entries[-1].event_type.value == "reserved"


def test_capability_mismatch_is_rejected(db_session):
    perf, pp, _, beneficiary, actor, role, op, types = _world(db_session)
    db_session.query(ActorRoleCapability).delete()
    db_session.commit()
    item = _item(db_session, beneficiary, types[0], "U-2")
    designation = _designation(db_session, perf, pp, beneficiary, actor, role, types[0])
    with pytest.raises(DesignationConflict, match="actor_role_capability_missing"):
        verify_self_designation(db_session, designation.id, item.id, op.id)


def test_top_three_item_only_designates_its_bound_actor(db_session):
    perf, pp, _, beneficiary, bound_actor, role, op, types = _world(db_session)
    other_actor = Actor(display_name="Other ranking actor")
    db_session.add(other_actor)
    db_session.flush()
    db_session.add(ActorRoleCapability(actor_id=other_actor.id, role_id=role.id))
    db_session.commit()
    item = _item(db_session, beneficiary, types[1], "TOP-BOUND", bound_actor=bound_actor)
    designation = _designation(
        db_session, perf, pp, beneficiary, other_actor, role, types[1]
    )

    with pytest.raises(DesignationConflict, match="entitlement_bound_actor_mismatch"):
        verify_self_designation(db_session, designation.id, item.id, op.id)


def test_proxy_owner_may_be_absent_but_requires_verification_and_exact_owner_item(db_session):
    perf, pp, owner, _, actor, role, op, types = _world(db_session)
    item = _item(db_session, owner, types[1], "P-1", bound_actor=actor)
    designation = _designation(db_session, perf, pp, owner, actor, role, types[1], "proxy")
    with pytest.raises(DesignationConflict, match="proxy_verification_required"):
        activate_predesignation(db_session, designation.id, op.id)
    result = verify_proxy_designation(
        db_session, designation.id, owner.id, item.id, "电话确认", op.id
    )
    assert result.lifecycle_status == "predesignated"
    assert result.verified_by == op.id and result.verification_note == "电话确认"
    assert item.owner_id == owner.id and item.current_designation_id == designation.id


def test_priority_conflicts_and_confirmed_atomic_replacement(db_session):
    perf, pp, _, beneficiary, actor, role, op, types = _world(db_session)
    low_item = _item(db_session, beneficiary, types[2], "LOW")
    low = _designation(db_session, perf, pp, beneficiary, actor, role, types[2])
    verify_self_designation(db_session, low.id, low_item.id, op.id)
    high_item = _item(db_session, beneficiary, types[0], "HIGH")
    high = _designation(db_session, perf, pp, beneficiary, actor, role, types[0])
    result = verify_self_designation(db_session, high.id, high_item.id, op.id)
    assert result.lifecycle_status == "pending_conflict"
    assert result.failure_reason == "designation_priority_higher"
    result = replace_predesignation(
        db_session, high.id, low.id, {"incoming": high.version, "replaced": low.version}, op.id
    )
    assert result.lifecycle_status == "predesignated"
    assert low.lifecycle_status == "replaced"
    assert low_item.status == EntitlementItemStatus.AVAILABLE
    assert high_item.status == EntitlementItemStatus.RESERVED


def test_lower_and_equal_priority_remain_pending_without_reservation(db_session):
    perf, pp, _, beneficiary, actor, role, op, types = _world(db_session)
    high_item = _item(db_session, beneficiary, types[0], "HI")
    high = _designation(db_session, perf, pp, beneficiary, actor, role, types[0])
    verify_self_designation(db_session, high.id, high_item.id, op.id)
    for typ, code in ((types[2], "LO"), (types[0], "EQ")):
        item = _item(db_session, beneficiary, typ, code)
        incoming = _designation(db_session, perf, pp, beneficiary, actor, role, typ)
        verify_self_designation(db_session, incoming.id, item.id, op.id)
        assert item.status == EntitlementItemStatus.AVAILABLE
        assert incoming.lifecycle_status == (
            "pending_conflict" if typ is types[2] else "manual_review"
        )


def test_cancel_releases_or_expires_with_audit_and_is_idempotent(db_session):
    perf, pp, _, beneficiary, actor, role, op, types = _world(db_session)
    item = _item(db_session, beneficiary, types[0], "C")
    designation = _designation(db_session, perf, pp, beneficiary, actor, role, types[0])
    verify_self_designation(db_session, designation.id, item.id, op.id)
    result = cancel_designation(db_session, designation.id, "场次取消", op.id)
    assert result.lifecycle_status == "cancelled" and item.status == EntitlementItemStatus.AVAILABLE
    assert item.ledger_entries[-1].reason == "场次取消"
    assert (
        cancel_designation(db_session, designation.id, "重复请求", op.id).lifecycle_status
        == "cancelled"
    )


def test_hard_workspace_conflict_blocks_designation_activation(db_session, monkeypatch):
    from app.schemas.designation_workspace import DesignationConflictProjection

    perf, pp, _, beneficiary, actor, role, op, types = _world(db_session)
    item = _item(db_session, beneficiary, types[0], "HARD")
    designation = _designation(db_session, perf, pp, beneficiary, actor, role, types[0])
    monkeypatch.setattr(
        "app.services.designations.project_designation_conflicts",
        lambda *_: [
            DesignationConflictProjection(
                code="MAX_CONSECUTIVE_EXCEEDED",
                severity="hard",
                message="超过演员个人最大连场数",
                designation_id=designation.id,
            )
        ],
    )

    with pytest.raises(DesignationConflict, match="designation_hard_conflict"):
        verify_self_designation(db_session, designation.id, item.id, op.id)


def test_refund_after_expiry_is_release_event_to_expired_state(db_session):
    perf, pp, _, beneficiary, actor, role, op, types = _world(db_session)
    item = _item(db_session, beneficiary, types[0], "EXPIRED-REFUND")
    row = _designation(db_session, perf, pp, beneficiary, actor, role, types[0])
    verify_self_designation(db_session, row.id, item.id, op.id)
    item.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db_session.flush()
    cancel_designation(db_session, row.id, "未满足", op.id)
    assert item.status == EntitlementItemStatus.EXPIRED
    assert item.ledger_entries[-1].event_type.value == "released"
    assert item.ledger_entries[-1].from_status == EntitlementItemStatus.RESERVED
    assert item.ledger_entries[-1].to_status == EntitlementItemStatus.EXPIRED


def test_role_must_belong_to_target_performance_theater_and_target_fields_agree(db_session):
    perf, pp, _, beneficiary, actor, role, op, types = _world(db_session)
    other = Theater(name="Other")
    db_session.add(other)
    db_session.flush()
    foreign_role = Role(theater_id=other.id, name="Foreign")
    db_session.add(foreign_role)
    db_session.flush()
    db_session.add(ActorRoleCapability(actor_id=actor.id, role_id=foreign_role.id))
    db_session.commit()
    item = _item(db_session, beneficiary, types[0], "SCOPE")
    row = _designation(db_session, perf, pp, beneficiary, actor, foreign_role, types[0])
    with pytest.raises(DesignationConflict, match="designation_role_outside_performance_theater"):
        verify_self_designation(db_session, row.id, item.id, op.id)
    row.role_id = role.id
    row.target_performance_id = perf.id + 999
    db_session.commit()
    with pytest.raises(DesignationConflict, match="designation_performance_scope_mismatch"):
        verify_self_designation(db_session, row.id, item.id, op.id)


def test_idempotency_replay_and_stale_different_key(db_session):
    perf, pp, _, beneficiary, actor, role, op, types = _world(db_session)
    item = _item(db_session, beneficiary, types[0], "IDEMP")
    row = _designation(db_session, perf, pp, beneficiary, actor, role, types[0])
    result = verify_self_designation(
        db_session, row.id, item.id, op.id, expected_version=1, idempotency_key="same"
    )
    db_session.commit()
    replay = verify_self_designation(
        db_session, row.id, item.id, op.id, expected_version=1, idempotency_key="same"
    )
    assert replay.id == result.id
    assert (
        db_session.query(DesignationLifecycleEvent)
        .filter_by(designation_id=row.id, action="verify_self")
        .count()
        == 1
    )
    with pytest.raises(DesignationConflict, match="designation_version_conflict"):
        verify_self_designation(
            db_session, row.id, item.id, op.id, expected_version=1, idempotency_key="different"
        )
    cancel_designation(
        db_session, row.id, "later", op.id, expected_version=row.version, idempotency_key="cancel"
    )
    replay = verify_self_designation(
        db_session, row.id, item.id, op.id, expected_version=1, idempotency_key="same"
    )
    assert replay.lifecycle_status == "predesignated"
    with pytest.raises(DesignationConflict, match="idempotency_conflict"):
        verify_self_designation(
            db_session, row.id, item.id, op.id, expected_version=999, idempotency_key="same"
        )


def test_caller_rollback_restores_designation_item_and_audits_on_flush_failure(
    db_session, monkeypatch
):
    perf, pp, _, beneficiary, actor, role, op, types = _world(db_session)
    item = _item(db_session, beneficiary, types[0], "ROLLBACK")
    row = _designation(db_session, perf, pp, beneficiary, actor, role, types[0])
    original_flush = db_session.flush

    def fail_flush(*args, **kwargs):
        raise RuntimeError("forced_audit_insert_failure")

    monkeypatch.setattr(db_session, "flush", fail_flush)
    with pytest.raises(RuntimeError, match="forced_audit_insert_failure"):
        verify_self_designation(
            db_session, row.id, item.id, op.id, expected_version=1, idempotency_key="rollback"
        )
    db_session.rollback()
    monkeypatch.setattr(db_session, "flush", original_flush)
    db_session.expire_all()
    assert db_session.get(Designation, row.id).lifecycle_status == "draft"
    assert db_session.get(EntitlementItem, item.id).status == EntitlementItemStatus.AVAILABLE
    assert db_session.query(DesignationLifecycleEvent).filter_by(designation_id=row.id).count() == 0


def test_activation_revalidates_item_and_capability_after_pending_conflict(db_session):
    perf, pp, _, beneficiary, actor, role, op, types = _world(db_session)
    occupied_item = _item(db_session, beneficiary, types[0], "OCC")
    occupied = _designation(db_session, perf, pp, beneficiary, actor, role, types[0])
    verify_self_designation(db_session, occupied.id, occupied_item.id, op.id)
    item = _item(db_session, beneficiary, types[2], "PEND")
    row = _designation(db_session, perf, pp, beneficiary, actor, role, types[2])
    verify_self_designation(db_session, row.id, item.id, op.id)
    cancel_designation(db_session, occupied.id, "clear", op.id)
    item.status = EntitlementItemStatus.REVOKED
    db_session.flush()
    with pytest.raises(DesignationConflict, match="entitlement_not_available"):
        activate_predesignation(db_session, row.id, op.id)
    item.status = EntitlementItemStatus.AVAILABLE
    db_session.query(ActorRoleCapability).delete()
    db_session.flush()
    with pytest.raises(DesignationConflict, match="actor_role_capability_missing"):
        activate_predesignation(db_session, row.id, op.id)


@pytest.mark.parametrize("decision", ["keep_occupied", "choose_incoming"])
def test_equal_priority_manual_choice_has_explicit_atomic_outcomes(db_session, decision):
    perf, pp, _, beneficiary, actor, role, op, types = _world(db_session)
    old_item = _item(db_session, beneficiary, types[0], "EQ-OLD")
    occupied = _designation(db_session, perf, pp, beneficiary, actor, role, types[0])
    verify_self_designation(db_session, occupied.id, old_item.id, op.id)
    new_item = _item(db_session, beneficiary, types[0], "EQ-NEW")
    incoming = _designation(db_session, perf, pp, beneficiary, actor, role, types[0])
    verify_self_designation(db_session, incoming.id, new_item.id, op.id)
    result = resolve_equal_priority(
        db_session,
        incoming.id,
        occupied.id,
        decision,
        {"incoming": incoming.version, "occupied": occupied.version},
        op.id,
        idempotency_key=decision,
    )
    if decision == "keep_occupied":
        assert (
            result.lifecycle_status == "pending_conflict"
            and old_item.status == EntitlementItemStatus.RESERVED
            and new_item.status == EntitlementItemStatus.AVAILABLE
        )
    else:
        assert (
            result.lifecycle_status == "predesignated" and occupied.lifecycle_status == "replaced"
        )
        assert (
            old_item.status == EntitlementItemStatus.AVAILABLE
            and new_item.status == EntitlementItemStatus.RESERVED
        )


def test_equal_choice_rejects_unrelated_or_broken_occupied_item(db_session):
    perf, pp, _, beneficiary, actor, role, op, types = _world(db_session)
    old_item = _item(db_session, beneficiary, types[0], "BAD-OLD")
    occupied = _designation(db_session, perf, pp, beneficiary, actor, role, types[0])
    verify_self_designation(db_session, occupied.id, old_item.id, op.id)
    new_item = _item(db_session, beneficiary, types[0], "BAD-NEW")
    incoming = _designation(db_session, perf, pp, beneficiary, actor, role, types[0])
    verify_self_designation(db_session, incoming.id, new_item.id, op.id)
    old_item.current_designation_id = 999
    db_session.flush()
    with pytest.raises(DesignationConflict, match="designation_occupied_item_invariant"):
        resolve_equal_priority(
            db_session,
            incoming.id,
            occupied.id,
            "choose_incoming",
            {"incoming": incoming.version, "occupied": occupied.version},
            op.id,
            idempotency_key="bad",
        )


@pytest.mark.parametrize("shared", ["role", "actor"])
def test_equal_choice_accepts_same_role_or_same_actor_conflict(db_session, shared):
    perf, pp, _, beneficiary, actor, role, op, types = _world(db_session)
    other_actor = Actor(display_name="Other Actor")
    other_role = Role(theater_id=role.theater_id, name="Other Role")
    db_session.add_all([other_actor, other_role])
    db_session.flush()
    db_session.add_all(
        [
            ActorRoleCapability(actor_id=other_actor.id, role_id=role.id),
            ActorRoleCapability(actor_id=actor.id, role_id=other_role.id),
        ]
    )
    db_session.commit()
    old_item = _item(db_session, beneficiary, types[0], f"OR-OLD-{shared}")
    occupied = _designation(db_session, perf, pp, beneficiary, actor, role, types[0])
    verify_self_designation(db_session, occupied.id, old_item.id, op.id)
    new_item = _item(db_session, beneficiary, types[0], f"OR-NEW-{shared}")
    incoming = _designation(
        db_session,
        perf,
        pp,
        beneficiary,
        other_actor if shared == "role" else actor,
        role if shared == "role" else other_role,
        types[0],
    )
    verify_self_designation(db_session, incoming.id, new_item.id, op.id)
    assert (
        resolve_equal_priority(
            db_session,
            incoming.id,
            occupied.id,
            "keep_occupied",
            {"incoming": incoming.version, "occupied": occupied.version},
            op.id,
            idempotency_key=f"or-{shared}",
        ).lifecycle_status
        == "pending_conflict"
    )


def test_equal_choice_rejects_completely_unrelated_same_performance(db_session):
    perf, pp, _, beneficiary, actor, role, op, types = _world(db_session)
    other_actor = Actor(display_name="Unrelated Actor")
    other_role = Role(theater_id=role.theater_id, name="Unrelated Role")
    db_session.add_all([other_actor, other_role])
    db_session.flush()
    db_session.add(ActorRoleCapability(actor_id=other_actor.id, role_id=other_role.id))
    db_session.commit()
    old_item = _item(db_session, beneficiary, types[0], "UNREL-OLD")
    occupied = _designation(db_session, perf, pp, beneficiary, actor, role, types[0])
    verify_self_designation(db_session, occupied.id, old_item.id, op.id)
    new_item = _item(db_session, beneficiary, types[0], "UNREL-NEW")
    incoming = _designation(db_session, perf, pp, beneficiary, other_actor, other_role, types[0])
    incoming.lifecycle_status = "manual_review"
    incoming.entitlement_item_id = new_item.id
    incoming.version += 1
    db_session.flush()
    with pytest.raises(DesignationConflict, match="designation_manual_choice_unrelated"):
        resolve_equal_priority(
            db_session,
            incoming.id,
            occupied.id,
            "keep_occupied",
            {"incoming": incoming.version, "occupied": occupied.version},
            op.id,
            idempotency_key="unrelated",
        )
