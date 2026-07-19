from datetime import date, datetime, time

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.entities import (
    Actor,
    ActorRoleCapability,
    EntitlementItem,
    EntitlementItemType,
    EntitlementLedgerEntry,
    Performance,
    PlayerProfile,
    Role,
    ScheduleAssignment,
    Theater,
    TheaterSlot,
    TheaterWeeklyTemplateEntry,
    WeeklyBatch,
)
from app.models.enums import (
    DesignationType,
    EntitlementEventType,
    EntitlementItemCategory,
    EntitlementItemStatus,
)
from app.models import entities


def test_actor_workspace_models_and_defaults_are_declared(db_session):
    assert hasattr(entities, "ActorTheaterMembership")
    assert hasattr(entities, "ActorNotificationTask")
    assert hasattr(entities, "ActorNotification")
    assert hasattr(entities, "SmsDelivery")
    assert hasattr(entities, "LeaveApplication")
    assert hasattr(entities, "LeaveApplicationDay")
    theater = Theater(name="测试剧场")
    db_session.add(theater)
    db_session.flush()
    assert theater.reveal_days_before == 1
    assert theater.actor_sms_enabled is False


def test_entitlement_definitions_are_scoped_to_theater(db_session):
    first = Theater(name="一号剧场")
    second = Theater(name="二号剧场")
    db_session.add_all([first, second])
    db_session.flush()
    db_session.add_all(
        [
            EntitlementItemType(
                theater_id=first.id,
                code="universal",
                display_name="万能指定",
                category=EntitlementItemCategory.DESIGNATION,
                designation_type=DesignationType.UNIVERSAL,
                priority=300,
                default_validity_days=90,
                is_active=True,
                sort_order=0,
            ),
            EntitlementItemType(
                theater_id=second.id,
                code="universal",
                display_name="万能指定",
                category=EntitlementItemCategory.DESIGNATION,
                designation_type=DesignationType.UNIVERSAL,
                priority=300,
                default_validity_days=90,
                is_active=True,
                sort_order=0,
            ),
        ]
    )
    db_session.commit()

    assert db_session.query(EntitlementItemType).count() == 2


def test_player_can_own_a_typed_entitlement_item(db_session):
    player = PlayerProfile(display_name="Jennifer", normalized_name="jennifer")
    top_three_type = EntitlementItemType(
        code="top_three",
        display_name="榜单前三指定",
        priority=2,
        default_validity_months=3,
    )
    item = EntitlementItem(
        serial_number="DT-202604-0001",
        owner=player,
        item_type=top_three_type,
        source_month=date(2026, 4, 1),
        source_label="四月热力榜",
        granted_at=datetime(2026, 5, 3, 10),
        expires_at=datetime(2026, 8, 3, 10),
        status=EntitlementItemStatus.AVAILABLE,
    )

    assert item.owner is player
    assert item.item_type.code == "top_three"

    db_session.add(item)
    db_session.commit()
    db_session.expire_all()

    persisted = db_session.get(EntitlementItem, item.id)
    assert persisted is not None
    assert persisted.owner.display_name == "Jennifer"
    assert persisted.item_type.code == "top_three"


def _persist_entitlement_with_ledger(db_session):
    item = EntitlementItem(
        serial_number="DT-202604-LEDGER",
        owner=PlayerProfile(display_name="Ledger Owner", normalized_name="ledger owner"),
        item_type=EntitlementItemType(
            code="ledger_test",
            display_name="Ledger Test",
            priority=0,
            default_validity_months=1,
        ),
        source_month=date(2026, 4, 1),
        source_label="Ledger Test",
        granted_at=datetime(2026, 5, 1),
        expires_at=datetime(2026, 6, 1),
        status=EntitlementItemStatus.AVAILABLE,
    )
    entry = EntitlementLedgerEntry(
        item=item,
        event_type=EntitlementEventType.GRANTED,
        occurred_at=datetime(2026, 5, 1),
    )
    db_session.add(entry)
    db_session.commit()
    return item, entry


def test_ledger_entry_cannot_be_orphaned_by_collection_mutation(db_session):
    item, entry = _persist_entitlement_with_ledger(db_session)

    item.ledger_entries.remove(entry)
    with pytest.raises(RuntimeError, match="entitlement ledger entries are append-only"):
        db_session.flush()
    db_session.rollback()

    assert db_session.get(EntitlementLedgerEntry, entry.id) is not None


def test_persisted_ledger_entry_cannot_be_updated(db_session):
    _, entry = _persist_entitlement_with_ledger(db_session)

    entry.note = "rewritten history"
    with pytest.raises(RuntimeError, match="entitlement ledger entries are append-only"):
        db_session.flush()
    db_session.rollback()

    assert db_session.get(EntitlementLedgerEntry, entry.id).note is None


def test_persisted_ledger_entry_cannot_be_deleted(db_session):
    _, entry = _persist_entitlement_with_ledger(db_session)

    db_session.delete(entry)
    with pytest.raises(RuntimeError, match="entitlement ledger entries are append-only"):
        db_session.flush()
    db_session.rollback()

    assert db_session.get(EntitlementLedgerEntry, entry.id) is not None


def test_item_deletion_cannot_erase_ledger_history(db_session):
    item, entry = _persist_entitlement_with_ledger(db_session)

    db_session.delete(item)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    assert db_session.get(EntitlementItem, item.id) is not None
    assert db_session.get(EntitlementLedgerEntry, entry.id) is not None


def test_actor_can_have_multiple_role_capabilities(db_session):
    actor = Actor(display_name="小展", max_consecutive_performances=3)
    theater_a = Theater(name="西幽剧场")
    theater_b = Theater(name="东幽剧场")
    db_session.add_all([actor, theater_a, theater_b])
    db_session.flush()
    role_a = Role(theater_id=theater_a.id, name="长离", group_name="女位")
    role_b = Role(theater_id=theater_b.id, name="长离", group_name="女位")
    db_session.add_all([role_a, role_b])
    db_session.flush()

    db_session.add_all(
        [
            ActorRoleCapability(actor_id=actor.id, role_id=role_a.id),
            ActorRoleCapability(actor_id=actor.id, role_id=role_b.id),
        ]
    )
    db_session.commit()

    refreshed = db_session.get(Actor, actor.id)
    assert {(cap.role.theater_id, cap.role.name) for cap in refreshed.role_capabilities} == {
        (theater_a.id, "长离"),
        (theater_b.id, "长离"),
    }


def test_theater_supports_ordered_slots_and_relational_weekly_template(db_session):
    theater = Theater(name="西幽剧场")
    db_session.add(theater)
    db_session.flush()
    slots = [
        TheaterSlot(theater_id=theater.id, name="午场", start_time=time(13), sort_order=1),
        TheaterSlot(theater_id=theater.id, name="下午场", start_time=time(16), sort_order=2),
        TheaterSlot(theater_id=theater.id, name="晚场", start_time=time(19), sort_order=3),
        TheaterSlot(theater_id=theater.id, name="夜场", start_time=time(21, 30), sort_order=4),
    ]
    db_session.add_all(slots)
    db_session.flush()
    db_session.add_all(
        [
            TheaterWeeklyTemplateEntry(
                theater_id=theater.id, weekday="monday", theater_slot_id=slot.id
            )
            for slot in slots
        ]
    )
    db_session.commit()

    refreshed = db_session.get(Theater, theater.id)
    assert refreshed.name == "西幽剧场"
    assert [slot.name for slot in refreshed.slots] == ["午场", "下午场", "晚场", "夜场"]
    assert len(refreshed.weekly_template_entries) == 4


def test_weekly_batch_owns_versioned_assignment_conflicts(db_session):
    theater = Theater(name="西安幽州剧场")
    actor = Actor(display_name="小展")
    db_session.add_all([theater, actor])
    db_session.flush()
    slot = TheaterSlot(theater_id=theater.id, name="早场", start_time=time(12, 30), sort_order=0)
    role = Role(theater_id=theater.id, name="柳知雨")
    db_session.add_all([slot, role])
    db_session.flush()
    performance = Performance(
        theater_id=theater.id,
        theater_slot_id=slot.id,
        performance_date=date(2026, 12, 28),
        slot_name_snapshot=slot.name,
        start_time_snapshot=slot.start_time,
    )
    batch = WeeklyBatch(theater_id=theater.id, week_start=date(2026, 12, 28))
    db_session.add_all([performance, batch])
    db_session.flush()
    assignment = ScheduleAssignment(
        weekly_batch_id=batch.id,
        performance_id=performance.id,
        role_id=role.id,
        actor_id=actor.id,
        source="manual",
        conflict_codes=["actor_on_leave"],
        requires_approval=True,
        approved=True,
    )
    db_session.add(assignment)
    db_session.commit()

    assert assignment.weekly_batch_id == batch.id
    assert assignment.conflict_codes == ["actor_on_leave"]
    assert batch.version == 1
    assert batch.updated_at is not None
    assert batch.published_at is None
