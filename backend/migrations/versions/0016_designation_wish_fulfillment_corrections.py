"""add designation and wish fulfillment correction foundation

Revision ID: 0016_fulfillment_corrections
Revises: 0015_actor_notification_settings
"""

from alembic import op
import sqlalchemy as sa


revision = "0016_fulfillment_corrections"
down_revision = "0015_actor_notification_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "designation_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("designation_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("player_name", sa.String(120), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("usage_type", sa.String(40), nullable=True),
        sa.Column("owner_player_id", sa.Integer(), nullable=True),
        sa.Column("entitlement_item_id", sa.Integer(), nullable=True),
        sa.Column("source_revision_id", sa.Integer(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("correction_reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["designation_id"], ["designations.id"]),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.ForeignKeyConstraint(["owner_player_id"], ["player_profiles.id"]),
        sa.ForeignKeyConstraint(["entitlement_item_id"], ["entitlement_items.id"]),
        sa.ForeignKeyConstraint(["source_revision_id"], ["performance_board_revisions.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.UniqueConstraint("designation_id", "version_number", name="uq_designation_version"),
    )
    op.create_index("ix_designation_versions_designation_id", "designation_versions", ["designation_id"])
    op.create_table(
        "wish_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("wish_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("player_name", sa.String(120), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("source_revision_id", sa.Integer(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("correction_reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["wish_id"], ["wishes.id"]),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.ForeignKeyConstraint(["source_revision_id"], ["performance_board_revisions.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.UniqueConstraint("wish_id", "version_number", name="uq_wish_version"),
    )
    op.create_index("ix_wish_versions_wish_id", "wish_versions", ["wish_id"])
    op.create_table(
        "fulfillment_failures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("operation", sa.String(60), nullable=False),
        sa.Column("business_kind", sa.String(40), nullable=False),
        sa.Column("business_id", sa.Integer(), nullable=False),
        sa.Column("performance_id", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(160), nullable=False, unique=True),
        sa.Column("error_code", sa.String(160), nullable=False),
        sa.Column("status", sa.String(40), server_default="pending", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("operator_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["performance_id"], ["performances.id"]),
        sa.ForeignKeyConstraint(["operator_user_id"], ["users.id"]),
    )
    op.create_index("ix_fulfillment_failures_operation", "fulfillment_failures", ["operation"])
    op.create_index("ix_fulfillment_failures_business_kind", "fulfillment_failures", ["business_kind"])
    op.create_index("ix_fulfillment_failures_business_id", "fulfillment_failures", ["business_id"])
    op.create_index("ix_fulfillment_failures_performance_id", "fulfillment_failures", ["performance_id"])
    with op.batch_alter_table("designations") as batch:
        batch.add_column(sa.Column("current_version_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_designations_current_version", "designation_versions", ["current_version_id"], ["id"])
    with op.batch_alter_table("wishes") as batch:
        batch.add_column(sa.Column("current_version_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_wishes_current_version", "wish_versions", ["current_version_id"], ["id"])
    with op.batch_alter_table("entitlement_ledger_entries") as batch:
        batch.add_column(sa.Column("reverses_entry_id", sa.Integer(), nullable=True))
        batch.create_unique_constraint("uq_entitlement_ledger_reversal", ["reverses_entry_id"])
        batch.create_foreign_key("fk_entitlement_ledger_reverses", "entitlement_ledger_entries", ["reverses_entry_id"], ["id"])
    if op.get_bind().dialect.name == "sqlite":
        for trigger, operation in (
            ("trg_entitlement_ledger_entries_no_update", "UPDATE"),
            ("trg_entitlement_ledger_entries_no_delete", "DELETE"),
        ):
            op.execute(
                sa.text(
                    f"CREATE TRIGGER {trigger} BEFORE {operation} ON entitlement_ledger_entries "
                    "BEGIN SELECT RAISE(ABORT, 'entitlement ledger entries are append-only'); END"
                )
            )


def downgrade() -> None:
    with op.batch_alter_table("entitlement_ledger_entries") as batch:
        batch.drop_constraint("fk_entitlement_ledger_reverses", type_="foreignkey")
        batch.drop_constraint("uq_entitlement_ledger_reversal", type_="unique")
        batch.drop_column("reverses_entry_id")
    with op.batch_alter_table("wishes") as batch:
        batch.drop_constraint("fk_wishes_current_version", type_="foreignkey")
        batch.drop_column("current_version_id")
    with op.batch_alter_table("designations") as batch:
        batch.drop_constraint("fk_designations_current_version", type_="foreignkey")
        batch.drop_column("current_version_id")
    op.drop_table("fulfillment_failures")
    op.drop_index("ix_wish_versions_wish_id", table_name="wish_versions")
    op.drop_table("wish_versions")
    op.drop_index("ix_designation_versions_designation_id", table_name="designation_versions")
    op.drop_table("designation_versions")
