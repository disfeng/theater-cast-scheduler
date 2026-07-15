"""add versioned weekly scheduling workspace

Revision ID: 0005_weekly_scheduling_workspace
Revises: 0004_multi_theater_configuration
Create Date: 2026-07-15
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_weekly_scheduling_workspace"
down_revision: str | None = "0004_multi_theater_configuration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    batch_columns = {column["name"] for column in sa.inspect(bind).get_columns("weekly_batches")}
    if "updated_at" not in batch_columns:
        op.add_column("weekly_batches", sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
    if "published_at" not in batch_columns:
        op.add_column("weekly_batches", sa.Column("published_at", sa.DateTime(), nullable=True))
    if "version" not in batch_columns:
        op.add_column("weekly_batches", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))

    op.execute(sa.text("DELETE FROM schedule_assignments"))
    inspector = sa.inspect(bind)
    assignment_columns = {column["name"] for column in inspector.get_columns("schedule_assignments")}
    unique_constraints = {constraint["name"] for constraint in inspector.get_unique_constraints("schedule_assignments")}
    foreign_keys = {constraint["name"] for constraint in inspector.get_foreign_keys("schedule_assignments")}
    indexes = {index["name"] for index in inspector.get_indexes("schedule_assignments")}
    with op.batch_alter_table("schedule_assignments") as batch:
        if "performance_id" in unique_constraints:
            batch.drop_constraint("performance_id", type_="unique")
        if "weekly_batch_id" not in assignment_columns:
            batch.add_column(sa.Column("weekly_batch_id", sa.Integer(), nullable=False))
        if "conflict_codes" not in assignment_columns:
            # MySQL rejects defaults on JSON columns, so add it nullable and backfill below.
            batch.add_column(sa.Column("conflict_codes", sa.JSON(), nullable=True))

    op.execute(sa.text("UPDATE schedule_assignments SET conflict_codes = '[]' WHERE conflict_codes IS NULL"))
    with op.batch_alter_table("schedule_assignments") as batch:
        batch.alter_column("conflict_codes", existing_type=sa.JSON(), nullable=False)
        if "fk_schedule_assignments_weekly_batch_id" not in foreign_keys:
            batch.create_foreign_key(
                "fk_schedule_assignments_weekly_batch_id",
                "weekly_batches",
                ["weekly_batch_id"],
                ["id"],
            )
        if "uq_schedule_assignment_batch_slot" not in unique_constraints:
            batch.create_unique_constraint(
                "uq_schedule_assignment_batch_slot",
                ["weekly_batch_id", "performance_id", "role_id"],
            )
        if "ix_schedule_assignments_weekly_batch_id" not in indexes:
            batch.create_index("ix_schedule_assignments_weekly_batch_id", ["weekly_batch_id"])


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM schedule_assignments"))
    with op.batch_alter_table("schedule_assignments") as batch:
        batch.drop_index("ix_schedule_assignments_weekly_batch_id")
        batch.drop_constraint("uq_schedule_assignment_batch_slot", type_="unique")
        batch.drop_constraint("fk_schedule_assignments_weekly_batch_id", type_="foreignkey")
        batch.drop_column("conflict_codes")
        batch.drop_column("weekly_batch_id")
        batch.create_unique_constraint("performance_id", ["performance_id", "role_id"])

    op.drop_column("weekly_batches", "version")
    op.drop_column("weekly_batches", "published_at")
    op.drop_column("weekly_batches", "updated_at")
