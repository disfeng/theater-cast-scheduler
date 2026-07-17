"""add monthly plan support

Revision ID: 0002_add_monthly_plan_support
Revises: 0001_initial_schema
Create Date: 2026-07-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_add_monthly_plan_support"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("performances") as batch:
        batch.create_unique_constraint(
            "uq_performance_theater_date_slot",
            ["theater_id", "performance_date", "slot"],
        )


def downgrade() -> None:
    with op.batch_alter_table("performances") as batch:
        batch.drop_constraint("uq_performance_theater_date_slot", type_="unique")
