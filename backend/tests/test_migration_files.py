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


def test_multi_theater_migration_normalizes_slots_roles_and_performances():
    migration = Path("migrations/versions/0004_multi_theater_configuration.py").read_text()

    assert 'down_revision: str | None = "0003_add_import_drafts"' in migration
    assert "theater_slots" in migration
    assert "theater_weekly_template_entries" in migration
    assert "theater_slot_id" in migration
    assert "slot_name_snapshot" in migration
    assert "start_time_snapshot" in migration
    assert "uq_roles_theater_name" in migration
    assert "uq_performance_theater_date_theater_slot" in migration
    assert 'op.execute(sa.text("DELETE FROM actor_role_capabilities"))' in migration
    assert 'op.execute(sa.text("DELETE FROM theaters"))' in migration
    assert 'DELETE FROM users' not in migration
    assert 'DELETE FROM actors' not in migration
