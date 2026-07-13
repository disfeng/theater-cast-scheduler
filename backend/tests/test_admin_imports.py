from datetime import date, datetime
import pytest
from sqlalchemy.exc import IntegrityError
from app.models.entities import Theater, WeeklyBatch, PersistentImportDraft, ImportDraftItem
from app.models.enums import BatchStatus, ImportDraftStatus, DraftItemKind, DraftValidationStatus, DesignationType

def test_weekly_batch_and_import_draft_relationships(db_session):
    theater = Theater(name="测试剧场", default_weekly_template={})
    db_session.add(theater)
    db_session.flush()

    batch = WeeklyBatch(theater_id=theater.id, week_start=date(2026, 6, 1))
    db_session.add(batch)
    db_session.flush()

    draft = PersistentImportDraft(weekly_batch_id=batch.id, raw_text="测试文本")
    db_session.add(draft)
    db_session.flush()

    item = ImportDraftItem(
        import_draft_id=draft.id,
        item_kind=DraftItemKind.UNRESOLVED,
        raw_line="浩泽 想要 演 长离"
    )
    db_session.add(item)
    db_session.commit()

    db_session.refresh(batch)
    db_session.refresh(draft)
    db_session.refresh(item)

    assert batch.status == BatchStatus.DRAFT
    assert draft.status == ImportDraftStatus.DRAFT
    assert item.validation_status == DraftValidationStatus.INVALID
    assert item.import_draft.id == draft.id
    assert draft.weekly_batch.id == batch.id

def test_duplicate_weekly_batches_raise_integrity_error(db_session):
    theater = Theater(name="测试剧场", default_weekly_template={})
    db_session.add(theater)
    db_session.flush()

    batch1 = WeeklyBatch(theater_id=theater.id, week_start=date(2026, 6, 1))
    batch2 = WeeklyBatch(theater_id=theater.id, week_start=date(2026, 6, 1))
    db_session.add(batch1)
    db_session.add(batch2)
    with pytest.raises(IntegrityError):
        db_session.commit()


from app.services.admin_imports import get_or_create_weekly_batch, parse_import_draft


def test_get_or_create_weekly_batch_validation_and_idempotency(db_session):
    theater = Theater(name="测试剧场", default_weekly_template={})
    db_session.add(theater)
    db_session.flush()

    # Non-Monday date should raise ValueError
    with pytest.raises(ValueError, match="week_start_must_be_monday"):
        get_or_create_weekly_batch(db_session, theater.id, date(2026, 6, 2))  # Tuesday

    # Creation
    batch1 = get_or_create_weekly_batch(db_session, theater.id, date(2026, 6, 1))
    db_session.commit()

    # Repeated query/creation returns existing
    batch2 = get_or_create_weekly_batch(db_session, theater.id, date(2026, 6, 1))
    assert batch1.id == batch2.id


def test_parse_import_draft_persists_items(db_session):
    theater = Theater(name="测试剧场", default_weekly_template={})
    db_session.add(theater)
    db_session.flush()

    batch = get_or_create_weekly_batch(db_session, theater.id, date(2026, 6, 1))
    db_session.commit()

    text = """
#指定信息⬇️
【虔诚许愿】-小展/长离-Jennifer 山风昭昭可以原地转十个圈
热力榜三-文轩/轩辕重光（四月热力榜-兹）
未知行：什么都没有匹配
"""
    draft = parse_import_draft(db_session, batch.id, text)
    db_session.commit()
    db_session.expire_all()

    # Verify persistent draft and its items
    refreshed_draft = db_session.get(PersistentImportDraft, draft.id)
    assert refreshed_draft is not None
    assert len(refreshed_draft.items) == 3

    # Check kind
    kinds = [item.item_kind for item in refreshed_draft.items]
    assert DraftItemKind.WISH in kinds
    assert DraftItemKind.DESIGNATION in kinds
    assert DraftItemKind.UNRESOLVED in kinds


from app.services.admin_imports import (
    create_manual_item,
    update_draft_item,
    confirm_draft_item,
    confirm_valid_items,
    get_batch_scheduling_inputs,
    DraftItemConflict,
)
from app.models.entities import Actor, Role, ActorRoleCapability, Performance, Designation, Wish
from app.schemas.admin_imports import DraftItemUpdate


def test_item_validation_and_corrections(db_session):
    # Setup theater, batch, actor, role, capability
    theater = Theater(name="测试剧场", default_weekly_template={})
    db_session.add(theater)
    db_session.flush()

    batch = get_or_create_weekly_batch(db_session, theater.id, date(2026, 6, 1))
    
    actor = Actor(display_name="浩泽")
    role = Role(name="长离")
    db_session.add_all([actor, role])
    db_session.flush()

    # Cap not added yet.
    draft = parse_import_draft(db_session, batch.id, "#指定信息\n【虔诚许愿】-浩泽/长离-Jerry 想要长离")
    db_session.commit()

    item = draft.items[0]
    # Should be invalid because of missing capability
    assert item.validation_status == DraftValidationStatus.INVALID
    assert item.failure_reason == "actor_role_capability_missing"

    # Fix capability
    cap = ActorRoleCapability(actor_id=actor.id, role_id=role.id)
    db_session.add(cap)
    db_session.commit()

    # Update item to trigger re-validation
    update_payload = DraftItemUpdate(
        item_kind=item.item_kind,
        designation_type=item.designation_type,
        player_name=item.player_name,
        actor_name_raw=item.actor_name_raw,
        role_name_raw=item.role_name_raw,
        actor_id=actor.id,
        role_id=role.id,
        note=item.note,
    )
    updated_item = update_draft_item(db_session, item.id, update_payload)
    db_session.commit()

    assert updated_item.validation_status == DraftValidationStatus.VALID
    assert updated_item.failure_reason is None


def test_performance_outside_batch_validation(db_session):
    theater = Theater(name="测试剧场", default_weekly_template={})
    other_theater = Theater(name="另一个剧场", default_weekly_template={})
    db_session.add_all([theater, other_theater])
    db_session.flush()

    batch = get_or_create_weekly_batch(db_session, theater.id, date(2026, 6, 1))

    # Performance belonging to another theater
    perf_other = Performance(theater_id=other_theater.id, performance_date=date(2026, 6, 1), slot="early")
    # Performance outside Monday to Sunday week range
    perf_outside = Performance(theater_id=theater.id, performance_date=date(2026, 6, 8), slot="early")
    
    actor = Actor(display_name="浩泽")
    role = Role(name="长离")
    db_session.add_all([perf_other, perf_outside, actor, role])
    db_session.flush()
    db_session.add(ActorRoleCapability(actor_id=actor.id, role_id=role.id))
    db_session.commit()

    draft = parse_import_draft(db_session, batch.id, "#指定信息\n【虔诚许愿】-浩泽/长离-Jerry")
    item = draft.items[0]

    # Convert to designation, and target invalid performance (wrong theater)
    payload = DraftItemUpdate(
        item_kind=DraftItemKind.DESIGNATION,
        designation_type=DesignationType.UNIVERSAL,
        player_name="Jerry",
        actor_name_raw="浩泽",
        role_name_raw="长离",
        actor_id=actor.id,
        role_id=role.id,
        target_performance_id=perf_other.id,
    )
    updated = update_draft_item(db_session, item.id, payload)
    assert updated.validation_status == DraftValidationStatus.INVALID
    assert updated.failure_reason == "performance_outside_batch"

    # Target outside date range performance
    payload.target_performance_id = perf_outside.id
    updated = update_draft_item(db_session, item.id, payload)
    assert updated.validation_status == DraftValidationStatus.INVALID
    assert updated.failure_reason == "performance_outside_batch"


def test_partial_confirmation_and_idempotency(db_session):
    theater = Theater(name="测试剧场", default_weekly_template={})
    db_session.add(theater)
    db_session.flush()

    batch = get_or_create_weekly_batch(db_session, theater.id, date(2026, 6, 1))
    actor = Actor(display_name="浩泽")
    role = Role(name="长离")
    db_session.add_all([actor, role])
    db_session.flush()
    db_session.add(ActorRoleCapability(actor_id=actor.id, role_id=role.id))
    db_session.commit()

    # Draft with one valid wish and one unresolved (invalid) designation
    draft = parse_import_draft(db_session, batch.id, "#指定信息\n【虔诚许愿】-浩泽/长离-Jerry\n未知行：无效数据")
    item_wish = next(i for i in draft.items if i.item_kind == DraftItemKind.WISH)
    item_unresolved = next(i for i in draft.items if i.item_kind == DraftItemKind.UNRESOLVED)

    assert item_wish.validation_status == DraftValidationStatus.VALID
    assert item_unresolved.validation_status == DraftValidationStatus.INVALID

    # Confirm the valid wish
    confirmed = confirm_draft_item(db_session, item_wish.id)
    db_session.commit()

    db_session.refresh(draft)
    assert draft.status == ImportDraftStatus.PARTIALLY_CONFIRMED
    assert db_session.query(Wish).count() == 1

    # Idempotent confirmation returns existing
    confirmed_again = confirm_draft_item(db_session, item_wish.id)
    assert confirmed.wish_id == confirmed_again.wish_id
    assert db_session.query(Wish).count() == 1

    # Confirming invalid item fails
    with pytest.raises(DraftItemConflict, match="draft_item_invalid"):
        confirm_draft_item(db_session, item_unresolved.id)

    # Correct invalid item to designation
    update_payload = DraftItemUpdate(
        item_kind=DraftItemKind.DESIGNATION,
        designation_type=DesignationType.UNIVERSAL,
        player_name="Jerry",
        actor_name_raw="浩泽",
        role_name_raw="长离",
        actor_id=actor.id,
        role_id=role.id,
    )
    corrected_item = update_draft_item(db_session, item_unresolved.id, update_payload)
    db_session.commit()

    assert corrected_item.validation_status == DraftValidationStatus.VALID

    # Confirm the corrected designation
    confirm_draft_item(db_session, corrected_item.id)
    db_session.commit()

    db_session.refresh(draft)
    assert draft.status == ImportDraftStatus.CONFIRMED
    assert db_session.query(Designation).count() == 1


def test_batch_scheduling_inputs(db_session):
    theater = Theater(name="测试剧场", default_weekly_template={})
    db_session.add(theater)
    db_session.flush()

    batch1 = get_or_create_weekly_batch(db_session, theater.id, date(2026, 6, 1))
    batch2 = get_or_create_weekly_batch(db_session, theater.id, date(2026, 6, 8))

    actor = Actor(display_name="浩泽")
    role = Role(name="长离")
    db_session.add_all([actor, role])
    db_session.flush()
    db_session.add(ActorRoleCapability(actor_id=actor.id, role_id=role.id))
    db_session.commit()

    # Confirmed records on batch1
    d1 = Designation(weekly_batch_id=batch1.id, designation_type=DesignationType.UNIVERSAL, player_name="Jerry", actor_id=actor.id, role_id=role.id, submitted_at=datetime.utcnow(), included_in_batch=True, status="confirmed")
    w1 = Wish(weekly_batch_id=batch1.id, player_name="Jerry", actor_id=actor.id, role_id=role.id, note="备注1")
    
    # Confirmed records on batch2 (should be excluded from batch1)
    d2 = Designation(weekly_batch_id=batch2.id, designation_type=DesignationType.UNIVERSAL, player_name="Tom", actor_id=actor.id, role_id=role.id, submitted_at=datetime.utcnow(), included_in_batch=True, status="confirmed")
    
    # Unconfirmed/not-included designations on batch1 (should be excluded)
    d1_unconfirmed = Designation(weekly_batch_id=batch1.id, designation_type=DesignationType.UNIVERSAL, player_name="Spike", actor_id=actor.id, role_id=role.id, submitted_at=datetime.utcnow(), included_in_batch=False, status="pending")

    db_session.add_all([d1, w1, d2, d1_unconfirmed])
    db_session.commit()

    inputs = get_batch_scheduling_inputs(db_session, batch1.id)
    assert len(inputs["designations"]) == 1
    assert inputs["designations"][0]["player_name"] == "Jerry"
    assert len(inputs["wishes"]) == 1
    assert inputs["wishes"][0]["player_name"] == "Jerry"
    assert w1.note == "备注1"
