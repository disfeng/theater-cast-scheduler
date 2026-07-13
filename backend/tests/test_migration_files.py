from pathlib import Path


def test_monthly_plan_migration_declares_unique_performance_slot_index():
    migration = Path("migrations/versions/0002_add_monthly_plan_support.py").read_text()

    assert "uq_performance_theater_date_slot" in migration
    assert "theater_id" in migration
    assert "performance_date" in migration
    assert "slot" in migration


def test_import_drafts_migration_declares_tables_columns_and_indexes():
    migration = Path("migrations/versions/0003_add_import_drafts.py").read_text()

    assert "weekly_batches" in migration
    assert "import_drafts" in migration
    assert "import_draft_items" in migration
    assert "weekly_batch_id" in migration
    assert "uq_weekly_batches_theater_week" in migration

