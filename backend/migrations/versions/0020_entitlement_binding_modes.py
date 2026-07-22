"""add entitlement binding modes and reset test entitlement data

Revision ID: 0020_entitlement_bindings
Revises: 0019_daily_publications
"""

from alembic import op
import sqlalchemy as sa


revision = "0020_entitlement_bindings"
down_revision = "0019_daily_publications"
branch_labels = None
depends_on = None


LEDGER_TRIGGERS = (
    ("trg_entitlement_ledger_entries_no_update", "UPDATE"),
    ("trg_entitlement_ledger_entries_no_delete", "DELETE"),
)


def _drop_ledger_triggers() -> None:
    for name, _ in LEDGER_TRIGGERS:
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {name}"))


def _create_ledger_triggers() -> None:
    dialect = op.get_bind().dialect.name
    for name, operation in LEDGER_TRIGGERS:
        if dialect == "sqlite":
            op.execute(sa.text(
                f"CREATE TRIGGER {name} BEFORE {operation} ON entitlement_ledger_entries "
                "BEGIN SELECT RAISE(ABORT, 'entitlement ledger entries are append-only'); END"
            ))
        else:
            op.execute(sa.text(
                f"CREATE TRIGGER {name} BEFORE {operation} ON entitlement_ledger_entries "
                "FOR EACH ROW SIGNAL SQLSTATE '45000' "
                "SET MESSAGE_TEXT = 'entitlement ledger entries are append-only'"
            ))


def upgrade() -> None:
    grant_mode = sa.Enum("BY_PLAYER", "BY_ACTOR", name="entitlementgrantmode")
    with op.batch_alter_table("entitlement_item_types") as batch:
        batch.add_column(sa.Column("binds_beneficiary", sa.Boolean(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("binds_actor", sa.Boolean(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("binding_locked_at", sa.DateTime(), nullable=True))
    with op.batch_alter_table("entitlement_grant_batches") as batch:
        batch.add_column(sa.Column("grant_mode", grant_mode, nullable=False, server_default="BY_PLAYER"))
        batch.create_index("ix_entitlement_grant_batches_grant_mode", ["grant_mode"])
    with op.batch_alter_table("entitlement_items") as batch:
        batch.add_column(sa.Column("binds_beneficiary_snapshot", sa.Boolean(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("binds_actor_snapshot", sa.Boolean(), nullable=False, server_default="0"))

    _drop_ledger_triggers()
    table_names = set(sa.inspect(op.get_bind()).get_table_names())
    if "designations" in table_names:
        op.execute(sa.text("UPDATE designations SET entitlement_item_id = NULL, lifecycle_status = 'draft' WHERE entitlement_item_id IS NOT NULL"))
    if "designation_versions" in table_names:
        op.execute(sa.text("UPDATE designation_versions SET entitlement_item_id = NULL WHERE entitlement_item_id IS NOT NULL"))
    if "designation_fulfillment_events" in table_names:
        op.execute(sa.text("UPDATE designation_fulfillment_events SET entitlement_item_id = NULL WHERE entitlement_item_id IS NOT NULL"))
    op.execute(sa.text("DELETE FROM entitlement_ledger_entries"))
    op.execute(sa.text("DELETE FROM entitlement_items"))
    op.execute(sa.text("DELETE FROM entitlement_grant_draft_items"))
    op.execute(sa.text("DELETE FROM entitlement_grant_batches"))
    op.execute(sa.text("DELETE FROM entitlement_item_types"))
    _create_ledger_triggers()

    defaults = (
        ("universal", "万能指定", "UNIVERSAL", 300, 0, 0, 0),
        ("top_three", "榜三指定", "TOP_THREE", 200, 0, 1, 1),
        ("paired", "对位指定", "PAIRED", 100, 1, 0, 2),
    )
    for code, name, designation_type, priority, binds_beneficiary, binds_actor, sort_order in defaults:
        op.execute(sa.text(
            "INSERT INTO entitlement_item_types "
            "(theater_id, code, display_name, category, designation_type, priority, "
            "default_validity_days, color, is_active, sort_order, binds_beneficiary, binds_actor) "
            "SELECT id, :code, :name, 'DESIGNATION', :designation_type, :priority, "
            "90, '#2f6fed', 1, :sort_order, :binds_beneficiary, :binds_actor FROM theaters"
        ).bindparams(
            code=code, name=name, designation_type=designation_type, priority=priority,
            sort_order=sort_order, binds_beneficiary=binds_beneficiary, binds_actor=binds_actor,
        ))


def downgrade() -> None:
    with op.batch_alter_table("entitlement_items") as batch:
        batch.drop_column("binds_actor_snapshot")
        batch.drop_column("binds_beneficiary_snapshot")
    with op.batch_alter_table("entitlement_grant_batches") as batch:
        batch.drop_index("ix_entitlement_grant_batches_grant_mode")
        batch.drop_column("grant_mode")
    with op.batch_alter_table("entitlement_item_types") as batch:
        batch.drop_column("binding_locked_at")
        batch.drop_column("binds_actor")
        batch.drop_column("binds_beneficiary")
