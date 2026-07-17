"""normalize multi-theater configuration

Revision ID: 0004_multi_theater_configuration
Revises: 0003_add_import_drafts
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_multi_theater_configuration"
down_revision: str | None = "0003_add_import_drafts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The user explicitly approved clearing non-auth business data. Preserve users and actors.
    op.execute(sa.text("DELETE FROM actor_role_capabilities"))
    for table in (
        "import_draft_items",
        "import_drafts",
        "schedule_assignments",
        "designations",
        "wishes",
        "leave_requests",
        "weekly_batches",
        "performances",
        "roles",
    ):
        op.execute(sa.text(f"DELETE FROM {table}"))
    op.execute(sa.text("DELETE FROM theaters"))

    inspector = sa.inspect(op.get_bind())
    theater_columns = {column["name"] for column in inspector.get_columns("theaters")}
    if "is_active" not in theater_columns:
        op.add_column(
            "theaters",
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
        op.create_index("ix_theaters_is_active", "theaters", ["is_active"])
    if "default_weekly_template" in theater_columns:
        op.drop_column("theaters", "default_weekly_template")

    if "theater_slots" not in inspector.get_table_names():
        op.create_table(
            "theater_slots",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("theater_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(80), nullable=False),
            sa.Column("start_time", sa.Time(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.ForeignKeyConstraint(["theater_id"], ["theaters.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("theater_id", "name", name="uq_theater_slots_theater_name"),
        )
        op.create_index("ix_theater_slots_theater_id", "theater_slots", ["theater_id"])
        op.create_index("ix_theater_slots_is_active", "theater_slots", ["is_active"])

    if "theater_weekly_template_entries" not in inspector.get_table_names():
        op.create_table(
            "theater_weekly_template_entries",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("theater_id", sa.Integer(), nullable=False),
            sa.Column("weekday", sa.String(12), nullable=False),
            sa.Column("theater_slot_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["theater_id"], ["theaters.id"]),
            sa.ForeignKeyConstraint(["theater_slot_id"], ["theater_slots.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "theater_id", "weekday", "theater_slot_id", name="uq_weekly_template_entry"
            ),
        )
        op.create_index(
            "ix_weekly_template_theater_id", "theater_weekly_template_entries", ["theater_id"]
        )
        op.create_index(
            "ix_weekly_template_slot_id", "theater_weekly_template_entries", ["theater_slot_id"]
        )

    inspector = sa.inspect(op.get_bind())
    role_columns = {column["name"] for column in inspector.get_columns("roles")}
    if "theater_id" not in role_columns:
        with op.batch_alter_table("roles") as batch:
            batch.drop_constraint("name", type_="unique")
            batch.add_column(sa.Column("theater_id", sa.Integer(), nullable=False))
            batch.add_column(
                sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true())
            )
            batch.create_foreign_key("fk_roles_theater_id", "theaters", ["theater_id"], ["id"])
            batch.create_unique_constraint("uq_roles_theater_name", ["theater_id", "name"])
            batch.create_index("ix_roles_theater_id", ["theater_id"])
            batch.create_index("ix_roles_is_active", ["is_active"])

    inspector = sa.inspect(op.get_bind())
    performance_columns = {column["name"] for column in inspector.get_columns("performances")}
    if "theater_slot_id" not in performance_columns:
        performance_indexes = {index["name"] for index in inspector.get_indexes("performances")}
        # MySQL may use the old composite unique index to support the theater FK.
        # Give that FK its own index before removing the legacy unique constraint.
        if "ix_performances_theater_id" not in performance_indexes:
            op.create_index("ix_performances_theater_id", "performances", ["theater_id"])
        with op.batch_alter_table("performances") as batch:
            batch.drop_constraint("uq_performance_theater_date_slot", type_="unique")
            if "ix_performances_slot" in performance_indexes:
                batch.drop_index("ix_performances_slot")
            batch.drop_column("slot")
            batch.add_column(sa.Column("theater_slot_id", sa.Integer(), nullable=False))
            batch.add_column(sa.Column("slot_name_snapshot", sa.String(80), nullable=False))
            batch.add_column(sa.Column("start_time_snapshot", sa.Time(), nullable=False))
            batch.create_foreign_key(
                "fk_performances_theater_slot_id", "theater_slots", ["theater_slot_id"], ["id"]
            )
            batch.create_index("ix_performances_theater_slot_id", ["theater_slot_id"])
            batch.create_unique_constraint(
                "uq_performance_theater_date_theater_slot",
                ["theater_id", "performance_date", "theater_slot_id"],
            )


def downgrade() -> None:
    with op.batch_alter_table("performances") as batch:
        batch.drop_constraint("uq_performance_theater_date_theater_slot", type_="unique")
        batch.drop_constraint("fk_performances_theater_slot_id", type_="foreignkey")
        batch.drop_index("ix_performances_theater_slot_id")
        batch.drop_column("start_time_snapshot")
        batch.drop_column("slot_name_snapshot")
        batch.drop_column("theater_slot_id")
        batch.add_column(sa.Column("slot", sa.String(20), nullable=False))
        batch.create_unique_constraint(
            "uq_performance_theater_date_slot", ["theater_id", "performance_date", "slot"]
        )
    with op.batch_alter_table("roles") as batch:
        batch.drop_constraint("uq_roles_theater_name", type_="unique")
        batch.drop_constraint("fk_roles_theater_id", type_="foreignkey")
        batch.drop_index("ix_roles_theater_id")
        batch.drop_index("ix_roles_is_active")
        batch.drop_column("is_active")
        batch.drop_column("theater_id")
        batch.create_unique_constraint("name", ["name"])
    op.drop_table("theater_weekly_template_entries")
    op.drop_table("theater_slots")
    op.add_column(
        "theaters",
        sa.Column("default_weekly_template", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.drop_index("ix_theaters_is_active", table_name="theaters")
    op.drop_column("theaters", "is_active")
