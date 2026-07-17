"""add import drafts

Revision ID: 0003_add_import_drafts
Revises: 0002_add_monthly_plan_support
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_add_import_drafts"
down_revision: str | None = "0002_add_monthly_plan_support"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create weekly_batches
    op.create_table(
        "weekly_batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("theater_id", sa.Integer(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["theater_id"], ["theaters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("theater_id", "week_start", name="uq_weekly_batches_theater_week"),
    )
    op.create_index("ix_weekly_batches_theater_id", "weekly_batches", ["theater_id"])
    op.create_index("ix_weekly_batches_week_start", "weekly_batches", ["week_start"])

    # 2. Create import_drafts
    op.create_table(
        "import_drafts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("weekly_batch_id", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["weekly_batch_id"], ["weekly_batches.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_drafts_weekly_batch_id", "import_drafts", ["weekly_batch_id"])

    # 3. Create import_draft_items
    op.create_table(
        "import_draft_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("import_draft_id", sa.Integer(), nullable=False),
        sa.Column("item_kind", sa.String(50), nullable=False),
        sa.Column("raw_line", sa.Text(), nullable=True),
        sa.Column("designation_type", sa.String(50), nullable=True),
        sa.Column("player_name", sa.String(120), nullable=True),
        sa.Column("actor_name_raw", sa.String(120), nullable=True),
        sa.Column("role_name_raw", sa.String(120), nullable=True),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("role_id", sa.Integer(), nullable=True),
        sa.Column("target_performance_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("validation_status", sa.String(50), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("designation_id", sa.Integer(), nullable=True),
        sa.Column("wish_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["import_draft_id"], ["import_drafts.id"]),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.ForeignKeyConstraint(["target_performance_id"], ["performances.id"]),
        sa.ForeignKeyConstraint(["designation_id"], ["designations.id"]),
        sa.ForeignKeyConstraint(["wish_id"], ["wishes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_import_draft_items_import_draft_id", "import_draft_items", ["import_draft_id"]
    )

    # 4. Add weekly_batch_id column to designations and wishes
    with op.batch_alter_table("designations") as batch:
        batch.add_column(sa.Column("weekly_batch_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_designations_weekly_batch_id",
            "weekly_batches",
            ["weekly_batch_id"],
            ["id"],
        )

    with op.batch_alter_table("wishes") as batch:
        batch.add_column(sa.Column("weekly_batch_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_wishes_weekly_batch_id",
            "weekly_batches",
            ["weekly_batch_id"],
            ["id"],
        )


def downgrade() -> None:
    # Remove columns and constraints
    with op.batch_alter_table("wishes") as batch:
        batch.drop_constraint("fk_wishes_weekly_batch_id", type_="foreignkey")
        batch.drop_column("weekly_batch_id")

    with op.batch_alter_table("designations") as batch:
        batch.drop_constraint("fk_designations_weekly_batch_id", type_="foreignkey")
        batch.drop_column("weekly_batch_id")

    # Drop tables
    op.drop_table("import_draft_items")
    op.drop_table("import_drafts")
    op.drop_table("weekly_batches")
