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
