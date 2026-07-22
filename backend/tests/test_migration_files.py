import os
from pathlib import Path
import subprocess

from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import entities  # noqa: F401
from app.models.entities import Designation, WeeklyBatch, Wish


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
    assert "DELETE FROM users" not in migration
    assert "DELETE FROM actors" not in migration


def test_weekly_scheduling_migration_versions_assignments_and_batches():
    migration = Path("migrations/versions/0005_weekly_scheduling_workspace.py").read_text()

    assert 'down_revision: str | None = "0004_multi_theater_configuration"' in migration
    assert "weekly_batch_id" in migration
    assert "conflict_codes" in migration
    assert "version" in migration
    assert "updated_at" in migration
    assert "published_at" in migration
    assert "uq_schedule_assignment_batch_slot" in migration
    assert 'sa.Column("conflict_codes", sa.JSON(), nullable=True)' in migration
    assert 'server_default="[]"' not in migration


def test_entitlement_inventory_advances_head_and_declares_inventory_tables():
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = script.get_revision("0006_entitlement_inventory")

    migration_text = Path(revision.path).read_text()
    assert all(name in migration_text for name in ("EXTENDED", "RESTORED", "ADJUSTED"))
    assert revision.down_revision == "0005_weekly_scheduling_workspace"


def test_all_migration_revision_ids_fit_alembic_version_column():
    script = ScriptDirectory.from_config(Config("alembic.ini"))

    assert all(len(revision.revision) <= 32 for revision in script.walk_revisions())


def test_entitlement_binding_modes_migration_declares_rules_without_resetting_inventory():
    migration = Path("migrations/versions/0020_entitlement_binding_modes.py").read_text()

    assert 'down_revision = "0019_daily_publications"' in migration
    for name in (
        "binds_beneficiary",
        "binds_actor",
        "binding_locked_at",
        "binds_beneficiary_snapshot",
        "binds_actor_snapshot",
        "grant_mode",
    ):
        assert name in migration
    assert "DELETE FROM entitlement_ledger_entries" not in migration
    assert "DELETE FROM entitlement_items" not in migration
    assert "UPDATE entitlement_item_types" in migration
    assert "UPDATE entitlement_items" in migration
    assert "UPDATE entitlement_grant_batches" in migration
    assert "DELETE FROM theaters" not in migration
    assert "DELETE FROM actors" not in migration
    assert "DELETE FROM player_profiles" not in migration


def test_upgrade_from_0019_preserves_entitlement_inventory_and_links(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'entitlement-binding-upgrade.db'}"
    environment = {**os.environ, "DATABASE_URL": database_url}
    subprocess.run(
        ["alembic", "upgrade", "0019_daily_publications"],
        check=True,
        env=environment,
        capture_output=True,
        text=True,
    )
    engine = create_engine(database_url)
    with engine.begin() as connection:
        theater_id = connection.execute(
            text("INSERT INTO theaters (name, is_active) VALUES ('Preserved Theater', 1) RETURNING id")
        ).scalar_one()
        actor_id = connection.execute(
            text(
                "INSERT INTO actors (display_name, max_consecutive_performances, rating_level) "
                "VALUES ('Preserved Actor', 3, 'NORMAL') RETURNING id"
            )
        ).scalar_one()
        role_id = connection.execute(
            text(
                "INSERT INTO roles (theater_id, name, group_name, is_active) "
                "VALUES (:theater_id, 'Preserved Role', NULL, 1) RETURNING id"
            ),
            {"theater_id": theater_id},
        ).scalar_one()
        player_id = connection.execute(
            text(
                "INSERT INTO player_profiles (display_name, normalized_name) "
                "VALUES ('Preserved Player', 'preserved player') RETURNING id"
            )
        ).scalar_one()
        type_id = connection.execute(
            text(
                "INSERT INTO entitlement_item_types "
                "(theater_id, code, display_name, category, designation_type, priority, default_validity_days) "
                "VALUES (:theater_id, 'legacy_top_three', '旧榜三指定', 'DESIGNATION', 'TOP_THREE', 200, 90) RETURNING id"
            ),
            {"theater_id": theater_id},
        ).scalar_one()
        batch_id = connection.execute(
            text(
                "INSERT INTO entitlement_grant_batches "
                "(theater_id, source_type, source_month, source_label, status, bound_actor_id) "
                "VALUES (:theater_id, 'MONTHLY_RANKING', '2026-06-01', '六月榜单', 'GRANTED', :actor_id) RETURNING id"
            ),
            {"theater_id": theater_id, "actor_id": actor_id},
        ).scalar_one()
        item_id = connection.execute(
            text(
                "INSERT INTO entitlement_items "
                "(theater_id, serial_number, owner_id, item_type_id, grant_batch_id, source_type, source_month, "
                "source_label, granted_at, expires_at, status, bound_actor_id) "
                "VALUES (:theater_id, 'PRESERVE-0001', :player_id, :type_id, :batch_id, 'MONTHLY_RANKING', "
                "'2026-06-01', '六月榜单', '2026-07-01', '2026-10-01', 'RESERVED', :actor_id) RETURNING id"
            ),
            {
                "theater_id": theater_id,
                "player_id": player_id,
                "type_id": type_id,
                "batch_id": batch_id,
                "actor_id": actor_id,
            },
        ).scalar_one()
        designation_id = connection.execute(
            text(
                "INSERT INTO designations "
                "(designation_type, player_name, role_id, actor_id, submitted_at, included_in_batch, status, "
                "owner_player_id, entitlement_item_id, lifecycle_status) "
                "VALUES ('TOP_THREE', 'Preserved Player', :role_id, :actor_id, '2026-07-01', 0, 'confirmed', "
                ":player_id, :item_id, 'reserved') RETURNING id"
            ),
            {"role_id": role_id, "actor_id": actor_id, "player_id": player_id, "item_id": item_id},
        ).scalar_one()
        connection.execute(
            text("UPDATE entitlement_items SET current_designation_id = :designation_id WHERE id = :item_id"),
            {"designation_id": designation_id, "item_id": item_id},
        )
        ledger_id = connection.execute(
            text(
                "INSERT INTO entitlement_ledger_entries "
                "(theater_id, item_id, event_type, to_status, designation_id, note) "
                "VALUES (:theater_id, :item_id, 'RESERVED', 'RESERVED', :designation_id, 'preserve me') RETURNING id"
            ),
            {"theater_id": theater_id, "item_id": item_id, "designation_id": designation_id},
        ).scalar_one()
    engine.dispose()

    subprocess.run(
        ["alembic", "upgrade", "head"],
        check=True,
        env=environment,
        capture_output=True,
        text=True,
    )
    with create_engine(database_url).connect() as connection:
        item = connection.execute(
            text(
                "SELECT current_designation_id, binds_beneficiary_snapshot, binds_actor_snapshot "
                "FROM entitlement_items WHERE id = :item_id"
            ),
            {"item_id": item_id},
        ).one()
        ledger = connection.execute(
            text("SELECT designation_id, note FROM entitlement_ledger_entries WHERE id = :ledger_id"),
            {"ledger_id": ledger_id},
        ).one()
        designation_item_id = connection.execute(
            text("SELECT entitlement_item_id FROM designations WHERE id = :designation_id"),
            {"designation_id": designation_id},
        ).scalar_one()
        grant_mode = connection.execute(
            text("SELECT grant_mode FROM entitlement_grant_batches WHERE id = :batch_id"),
            {"batch_id": batch_id},
        ).scalar_one()
    assert item == (designation_id, 0, 1)
    assert ledger == (designation_id, "preserve me")
    assert designation_item_id == item_id
    assert grant_mode == "BY_ACTOR"


def test_theater_entitlement_management_is_migration_head():
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = script.get_revision("0012_theater_entitlements")

    assert script.get_current_head() == "0023_query_hardening"
    assert revision.down_revision == "0011_weekly_publish_operations"
    migration = Path(revision.path).read_text()
    for required in (
        "theater_id",
        "category",
        "designation_type",
        "default_validity_days",
        "source_type",
        "purpose",
    ):
        assert required in migration


def test_top_three_actor_binding_advances_migration_head():
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = script.get_revision("0013_top_three_actor_binding")

    assert script.get_current_head() == "0023_query_hardening"
    assert revision.down_revision == "0012_theater_entitlements"
    migration = Path(revision.path).read_text()
    assert "bound_actor_id" in migration
    assert "actors" in migration


def test_actor_workspace_migration_advances_head_and_declares_tables():
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = script.get_revision("0014_actor_mobile_workspace")

    assert script.get_current_head() == "0023_query_hardening"
    assert revision.down_revision == "0013_top_three_actor_binding"
    migration = Path(revision.path).read_text()
    for table in (
        "actor_theater_memberships",
        "actor_notification_tasks",
        "actor_notifications",
        "sms_deliveries",
        "leave_applications",
        "leave_application_days",
    ):
        assert table in migration


def test_performance_board_migration_advances_head_and_declares_contract():
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    head = script.get_current_head()
    revision = script.get_revision("0007_performance_boards")

    assert head == "0023_query_hardening"
    assert revision.down_revision == "0006_entitlement_inventory"
    migration = Path(revision.path).read_text()
    for table in (
        "performance_boards",
        "performance_board_revisions",
        "performance_players",
        "board_draft_items",
    ):
        assert table in migration
    for column in (
        "performance_id",
        "beneficiary_performance_player_id",
        "owner_player_id",
        "entitlement_item_id",
        "usage_type",
        "verification_status",
        "lifecycle_status",
        "performance_player_id",
    ):
        assert column in migration

    ai_revision = script.get_revision("0008_ai_parser_settings")
    assert ai_revision.down_revision == "0007_performance_boards"
    ai_migration = Path(ai_revision.path).read_text()
    assert "ai_parser_settings" in ai_migration
    assert "encrypted_api_key" in ai_migration
    lifecycle_revision = script.get_revision("0009_designation_lifecycle")
    assert lifecycle_revision.down_revision == "0008_ai_parser_settings"
    lifecycle_migration = Path(lifecycle_revision.path).read_text()
    assert "version" in lifecycle_migration
    assert "designation_lifecycle_events" in lifecycle_migration
    assert "uq_designation_action_idempotency" in lifecycle_migration
    assert "UPDATE designations SET lifecycle_status" in lifecycle_migration
    assert "UPDATE designations SET verification_status" in lifecycle_migration
    assert "UPDATE designations SET usage_type" in lifecycle_migration
    wish_revision = script.get_revision("0010_wish_lifecycle")
    assert wish_revision.down_revision == lifecycle_revision.revision
    wish_migration = Path(wish_revision.path).read_text()
    assert "wish_lifecycle_events" in wish_migration
    publish_revision = script.get_revision("0011_weekly_publish_operations")
    assert publish_revision.down_revision == wish_revision.revision
    publish_migration = Path(publish_revision.path).read_text()
    assert "weekly_publish_operations" in publish_migration
    assert "unmet_scope_hash" in publish_migration
    assert "response_snapshot" in publish_migration
    assert "uq_wish_active_scope_key" in wish_migration


def test_query_hardening_migration_adds_reversible_composite_indexes():
    migration = Path("migrations/versions/0023_query_hardening.py").read_text()
    expected = {
        "ix_performances_theater_date_status",
        "ix_entitlement_items_theater_owner_status",
        "ix_entitlement_items_theater_type_status_expiry",
        "ix_entitlement_ledger_theater_id",
        "ix_leave_days_status_date",
        "ix_schedule_assignments_actor_performance",
    }
    assert all(name in migration for name in expected)
    assert migration.count("op.create_index") == migration.count("op.drop_index")


def test_performance_board_sqlite_constraints_reject_cross_board_scope(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'board-scope.db'}"
    subprocess.run(
        ["alembic", "upgrade", "head"],
        check=True,
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
    )
    engine = create_engine(database_url)
    reflected_designation_fks = {
        fk["name"]: (tuple(fk["constrained_columns"]), fk["referred_table"])
        for fk in inspect(engine).get_foreign_keys("designations")
    }
    expected_designation_fks = {
        "fk_designations_performance": (("performance_id",), "performances"),
        "fk_designations_beneficiary_performance_player": (
            ("beneficiary_performance_player_id",),
            "performance_players",
        ),
        "fk_designations_owner_player": (("owner_player_id",), "player_profiles"),
        "fk_designations_entitlement_item": (("entitlement_item_id",), "entitlement_items"),
        "fk_designations_verified_by": (("verified_by",), "users"),
        "fk_designations_replaced_designation": (("replaced_designation_id",), "designations"),
    }
    assert expected_designation_fks.items() <= reflected_designation_fks.items()
    reflected_wish_fks = {
        fk["name"]: (tuple(fk["constrained_columns"]), fk["referred_table"])
        for fk in inspect(engine).get_foreign_keys("wishes")
    }
    expected_wish_fks = {
        "fk_wishes_performance": (("performance_id",), "performances"),
        "fk_wishes_performance_player": (("performance_player_id",), "performance_players"),
    }
    assert expected_wish_fks.items() <= reflected_wish_fks.items()
    metadata_engine = create_engine(f"sqlite:///{tmp_path / 'metadata-scope.db'}")
    Base.metadata.create_all(metadata_engine)
    metadata_inspector = inspect(metadata_engine)
    for table_name, expected in (
        ("designations", expected_designation_fks),
        ("wishes", expected_wish_fks),
    ):
        metadata_fks = {
            fk["name"]: (tuple(fk["constrained_columns"]), fk["referred_table"])
            for fk in metadata_inspector.get_foreign_keys(table_name)
        }
        assert expected.items() <= metadata_fks.items()
    with engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1
        connection.execute(text("INSERT INTO theaters (name, is_active) VALUES ('T', 1)"))
        theater_id = connection.scalar(text("SELECT id FROM theaters WHERE name='T'"))
        connection.execute(
            text(
                "INSERT INTO theater_slots (theater_id,name,start_time,sort_order,is_active) VALUES (:t,'S','19:30:00',0,1)"
            ),
            {"t": theater_id},
        )
        slot_id = connection.scalar(text("SELECT id FROM theater_slots WHERE name='S'"))
        for day in ("2026-09-01", "2026-09-02"):
            connection.execute(
                text(
                    "INSERT INTO performances (theater_id,theater_slot_id,performance_date,slot_name_snapshot,start_time_snapshot,status) VALUES (:t,:s,:d,'S','19:30:00','DRAFT')"
                ),
                {"t": theater_id, "s": slot_id, "d": day},
            )
        performance_ids = [
            row[0] for row in connection.execute(text("SELECT id FROM performances ORDER BY id"))
        ]
        for performance_id in performance_ids:
            connection.execute(
                text(
                    "INSERT INTO performance_boards (performance_id,next_revision_number) VALUES (:p,2)"
                ),
                {"p": performance_id},
            )
        board_ids = [
            row[0]
            for row in connection.execute(text("SELECT id FROM performance_boards ORDER BY id"))
        ]
        for board_id in board_ids:
            connection.execute(
                text(
                    "INSERT INTO performance_board_revisions (board_id,revision_number,raw_text,status,parser_type) VALUES (:b,1,'x','REVIEW_REQUIRED','DETERMINISTIC')"
                ),
                {"b": board_id},
            )
        revision_ids = [
            row[0]
            for row in connection.execute(
                text("SELECT id FROM performance_board_revisions ORDER BY id")
            )
        ]
        connection.commit()
        with pytest.raises(IntegrityError):
            connection.execute(
                text("UPDATE performance_boards SET current_revision_id=:r WHERE id=:b"),
                {"r": revision_ids[1], "b": board_ids[0]},
            )
            connection.commit()
        connection.rollback()
    engine.dispose()
    environment = {**os.environ, "DATABASE_URL": database_url}
    subprocess.run(
        ["alembic", "downgrade", "0011_weekly_publish_operations"],
        check=True,
        env=environment,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["alembic", "upgrade", "head"],
        check=True,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert "performance_boards" in inspect(create_engine(database_url)).get_table_names()


def test_entitlement_migration_contract_and_round_trip(tmp_path):
    database_path = tmp_path / "entitlement-contract.db"
    database_url = f"sqlite:///{database_path}"
    environment = {**os.environ, "DATABASE_URL": database_url}

    subprocess.run(
        ["alembic", "upgrade", "head"],
        check=True,
        env=environment,
        capture_output=True,
        text=True,
    )

    engine = create_engine(database_url)
    inspector = inspect(engine)
    expected_tables = {
        "player_profiles",
        "player_aliases",
        "entitlement_item_types",
        "entitlement_grant_batches",
        "entitlement_grant_draft_items",
        "entitlement_items",
        "entitlement_ledger_entries",
    }
    assert expected_tables <= set(inspector.get_table_names())

    with engine.connect() as connection:
        definitions = connection.execute(
            text("SELECT code, priority FROM entitlement_item_types ORDER BY priority")
        ).all()
    assert definitions == []

    with engine.connect() as connection:
        trigger_names = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'trigger' AND tbl_name = 'entitlement_ledger_entries'"
                )
            )
        }
    expected_triggers = {
        "trg_entitlement_ledger_entries_no_update",
        "trg_entitlement_ledger_entries_no_delete",
    }
    assert expected_triggers <= trigger_names

    with engine.begin() as connection:
        theater_id = connection.execute(
            text("INSERT INTO theaters (name, is_active) VALUES ('权益测试剧场', 1) RETURNING id")
        ).scalar_one()
        player_id = connection.execute(
            text(
                "INSERT INTO player_profiles (display_name, normalized_name) "
                "VALUES ('Trigger Owner', 'trigger owner') RETURNING id"
            )
        ).scalar_one()
        type_id = connection.execute(
            text(
                "INSERT INTO entitlement_item_types "
                "(theater_id, code, display_name, category, designation_type, priority, default_validity_days) "
                "VALUES (:theater_id, 'universal', '万能指定', 'DESIGNATION', 'UNIVERSAL', 300, 90) RETURNING id"
            ),
            {"theater_id": theater_id},
        ).scalar_one()
        item_id = connection.execute(
            text(
                "INSERT INTO entitlement_items "
                "(theater_id, serial_number, owner_id, item_type_id, source_type, source_month, source_label, granted_at, expires_at) "
                "VALUES (:theater_id, 'TRIGGER-0001', :owner_id, :type_id, 'OTHER', '2026-04-01', 'Trigger Test', "
                "'2026-05-01 00:00:00', '2026-08-01 00:00:00') RETURNING id"
            ),
            {"theater_id": theater_id, "owner_id": player_id, "type_id": type_id},
        ).scalar_one()
        ledger_id = connection.execute(
            text(
                "INSERT INTO entitlement_ledger_entries (theater_id, item_id, event_type, note) "
                "VALUES (:theater_id, :item_id, 'GRANTED', NULL) RETURNING id"
            ),
            {"theater_id": theater_id, "item_id": item_id},
        ).scalar_one()

    with engine.connect() as connection:
        with pytest.raises(DBAPIError, match="entitlement ledger entries are append-only"):
            connection.execute(
                text("UPDATE entitlement_ledger_entries SET note = 'tampered' WHERE id = :id"),
                {"id": ledger_id},
            )
        connection.rollback()
        with pytest.raises(DBAPIError, match="entitlement ledger entries are append-only"):
            connection.execute(
                text("DELETE FROM entitlement_ledger_entries WHERE id = :id"),
                {"id": ledger_id},
            )
        connection.rollback()

    with engine.connect() as connection:
        ledger_row = connection.execute(
            text("SELECT note FROM entitlement_ledger_entries WHERE id = :id"), {"id": ledger_id}
        ).one()
    assert ledger_row.note is None

    aliases_uniques = {
        tuple(item["column_names"]) for item in inspector.get_unique_constraints("player_aliases")
    }
    type_uniques = {
        tuple(item["column_names"])
        for item in inspector.get_unique_constraints("entitlement_item_types")
    }
    item_uniques = {
        tuple(item["column_names"])
        for item in inspector.get_unique_constraints("entitlement_items")
    }
    assert ("normalized_alias",) in aliases_uniques
    assert "is_primary" in {item["name"] for item in inspector.get_columns("player_aliases")}
    assert ("theater_id", "code") in type_uniques
    assert ("serial_number",) in item_uniques

    type_checks = {
        item["name"] for item in inspector.get_check_constraints("entitlement_item_types")
    }
    assert "ck_entitlement_item_types_priority_non_negative" in type_checks
    assert "ck_entitlement_types_validity_positive" in type_checks
    assert "ck_entitlement_types_category_binding" in type_checks

    ledger_columns = {
        item["name"]: item for item in inspector.get_columns("entitlement_ledger_entries")
    }
    item_columns = {item["name"]: item for item in inspector.get_columns("entitlement_items")}
    batch_columns = {
        item["name"]: item for item in inspector.get_columns("entitlement_grant_batches")
    }
    draft_columns = {
        item["name"]: item for item in inspector.get_columns("entitlement_grant_draft_items")
    }
    assert {
        "title",
        "grant_date",
        "default_expires_at",
        "notes",
        "created_by",
        "confirmed_by",
        "confirmed_at",
        "theater_id",
        "source_type",
        "idempotency_key",
        "bound_actor_id",
    } <= batch_columns.keys()
    assert {
        "batch_id",
        "player_id",
        "item_type_id",
        "source_month",
        "source_label",
        "expires_at",
        "notes",
        "bound_actor_id",
    } <= draft_columns.keys()
    assert {"notes", "theater_id", "source_type", "bound_actor_id"} <= item_columns.keys()
    assert {
        "from_status",
        "to_status",
        "performance_id",
        "designation_id",
        "reason",
        "operator_user_id",
        "theater_id",
        "purpose",
    } <= ledger_columns.keys()
    assert ledger_columns["item_id"]["nullable"] is False
    assert item_columns["current_designation_id"]["nullable"] is True
    ledger_foreign_keys = inspector.get_foreign_keys("entitlement_ledger_entries")
    assert any(
        key["constrained_columns"] == ["item_id"]
        and key["referred_table"] == "entitlement_items"
        and key["options"].get("ondelete") is None
        for key in ledger_foreign_keys
    )

    for table_name, columns in (
        ("player_profiles", ("status", "created_at")),
        ("entitlement_grant_batches", ("status", "created_at")),
        ("entitlement_items", ("status",)),
        ("entitlement_ledger_entries", ("occurred_at",)),
    ):
        reflected = {item["name"]: item for item in inspector.get_columns(table_name)}
        assert all(reflected[column]["default"] is not None for column in columns)

    engine.dispose()
    subprocess.run(
        ["alembic", "downgrade", "0005"],
        check=True,
        env=environment,
        capture_output=True,
        text=True,
    )
    downgraded_tables = set(inspect(create_engine(database_url)).get_table_names())
    assert expected_tables.isdisjoint(downgraded_tables)
    with create_engine(database_url).connect() as connection:
        remaining_triggers = connection.execute(
            text("SELECT name FROM sqlite_master WHERE type = 'trigger'")
        ).all()
    assert remaining_triggers == []
    subprocess.run(
        ["alembic", "upgrade", "head"],
        check=True,
        env=environment,
        capture_output=True,
        text=True,
    )

    with create_engine(database_url).connect() as connection:
        reseeded = connection.execute(
            text("SELECT code, priority FROM entitlement_item_types ORDER BY priority")
        ).all()
    assert reseeded == [("paired", 100), ("top_three", 200), ("universal", 300)]


def test_upgrade_from_0005_preserves_representative_legacy_rows(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'legacy-upgrade.db'}"
    environment = {**os.environ, "DATABASE_URL": database_url}
    subprocess.run(
        ["alembic", "upgrade", "0005"], check=True, env=environment, capture_output=True, text=True
    )
    engine = create_engine(database_url)
    with engine.begin() as connection:
        theater_id = connection.execute(
            text("INSERT INTO theaters (name,is_active) VALUES ('Legacy Theater',1) RETURNING id")
        ).scalar_one()
        role_id = connection.execute(
            text(
                "INSERT INTO roles (theater_id,name,group_name,is_active) "
                "VALUES (:theater,'Legacy Role',NULL,1) RETURNING id"
            ),
            {"theater": theater_id},
        ).scalar_one()
        actor_id = connection.execute(
            text(
                "INSERT INTO actors (display_name,max_consecutive_performances,rating_level) "
                "VALUES ('Legacy Actor',3,'NORMAL') RETURNING id"
            )
        ).scalar_one()
        batch_id = connection.execute(
            text(
                "INSERT INTO weekly_batches (theater_id,week_start,status,created_at,updated_at,version) "
                "VALUES (:theater,'2026-07-13','READY','2026-07-13','2026-07-13',1) RETURNING id"
            ),
            {"theater": theater_id},
        ).scalar_one()
        connection.execute(
            text(
                "INSERT INTO designations (designation_type,player_name,role_id,actor_id,submitted_at,"
                "included_in_batch,status,weekly_batch_id) VALUES "
                "('UNIVERSAL','Legacy Player',:role,:actor,'2026-07-13',1,'confirmed',:batch)"
            ),
            {"role": role_id, "actor": actor_id, "batch": batch_id},
        )
        connection.execute(
            text(
                "INSERT INTO wishes (player_name,role_id,actor_id,note,weekly_batch_id) "
                "VALUES ('Legacy Player',:role,:actor,'legacy wish',:batch)"
            ),
            {"role": role_id, "actor": actor_id, "batch": batch_id},
        )
    engine.dispose()

    subprocess.run(
        ["alembic", "upgrade", "head"], check=True, env=environment, capture_output=True, text=True
    )
    current_engine = create_engine(database_url)
    with Session(current_engine) as session:
        batch = session.get(WeeklyBatch, batch_id)
        designation = session.query(Designation).one()
        wish = session.query(Wish).one()
    assert str(batch.week_start) == "2026-07-13" and batch.version == 1
    assert designation.player_name == "Legacy Player" and designation.weekly_batch_id == batch_id
    assert designation.lifecycle_status == "legacy_review_required"
    assert wish.player_name == "Legacy Player" and wish.weekly_batch_id == batch_id
    assert wish.status == "legacy_review_required"
    assert wish.note == "legacy wish"


def test_upgrade_tolerates_designation_lifecycle_schema_created_ahead_of_alembic(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'schema-drift-upgrade.db'}"
    environment = {**os.environ, "DATABASE_URL": database_url}
    subprocess.run(
        ["alembic", "upgrade", "0008_ai_parser_settings"],
        check=True,
        env=environment,
        capture_output=True,
        text=True,
    )
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE designations ADD COLUMN version INTEGER NOT NULL DEFAULT 1")
        )
        connection.execute(
            text(
                "CREATE TABLE designation_lifecycle_events ("
                "id INTEGER PRIMARY KEY, designation_id INTEGER NOT NULL, "
                "operator_user_id INTEGER NOT NULL, action VARCHAR(40) NOT NULL, "
                "idempotency_key VARCHAR(120) NOT NULL, request_hash VARCHAR(64) NOT NULL, "
                "result_snapshot JSON NOT NULL, from_status VARCHAR(40), to_status VARCHAR(40), "
                "entitlement_item_id INTEGER, conflict_designation_id INTEGER, note TEXT, "
                "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "CONSTRAINT uq_designation_action_idempotency "
                "UNIQUE (designation_id, action, idempotency_key))"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX ix_designation_lifecycle_events_designation_id "
                "ON designation_lifecycle_events (designation_id)"
            )
        )
    engine.dispose()

    subprocess.run(
        ["alembic", "upgrade", "head"],
        check=True,
        env=environment,
        capture_output=True,
        text=True,
    )
    inspector = inspect(create_engine(database_url))
    assert "weekly_publish_operations" in inspector.get_table_names()
    assert [column["name"] for column in inspector.get_columns("designations")].count(
        "version"
    ) == 1
