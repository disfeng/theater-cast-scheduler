from datetime import date
import pytest
from sqlalchemy.exc import IntegrityError
from app.models.entities import Theater, WeeklyBatch, PersistentImportDraft, ImportDraftItem
from app.models.enums import BatchStatus, ImportDraftStatus, DraftItemKind, DraftValidationStatus

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
