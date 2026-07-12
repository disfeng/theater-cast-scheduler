from pathlib import Path


def test_monthly_plan_migration_declares_unique_performance_slot_index():
    migration = Path("migrations/versions/0002_add_monthly_plan_support.py").read_text()

    assert "uq_performance_theater_date_slot" in migration
    assert "theater_id" in migration
    assert "performance_date" in migration
    assert "slot" in migration
