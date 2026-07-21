"""add daily schedule publication snapshots

Revision ID: 0019_daily_publications
Revises: 0018_admin_scope_audit
"""

from alembic import op
import sqlalchemy as sa


revision = "0019_daily_publications"
down_revision = "0018_admin_scope_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "performance_cast_publications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("performance_id", sa.Integer(), nullable=False),
        sa.Column("theater_id", sa.Integer(), nullable=False),
        sa.Column("weekly_batch_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_batch_version", sa.Integer(), nullable=False),
        sa.Column("assignment_hash", sa.String(64), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=False),
        sa.Column("operator_user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["performance_id"], ["performances.id"]),
        sa.ForeignKeyConstraint(["theater_id"], ["theaters.id"]),
        sa.ForeignKeyConstraint(["weekly_batch_id"], ["weekly_batches.id"]),
        sa.ForeignKeyConstraint(["operator_user_id"], ["users.id"]),
        sa.UniqueConstraint("performance_id", name="uq_performance_cast_publication"),
    )
    for column in ("performance_id", "theater_id", "weekly_batch_id", "operator_user_id"):
        op.create_index(f"ix_performance_cast_publications_{column}", "performance_cast_publications", [column])

    op.create_table(
        "published_cast_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("publication_id", sa.Integer(), nullable=False),
        sa.Column("performance_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(40), nullable=False, server_default="manual"),
        sa.ForeignKeyConstraint(["publication_id"], ["performance_cast_publications.id"]),
        sa.ForeignKeyConstraint(["performance_id"], ["performances.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"]),
        sa.UniqueConstraint("publication_id", "role_id", name="uq_published_cast_role"),
    )
    for column in ("publication_id", "performance_id", "role_id", "actor_id"):
        op.create_index(f"ix_published_cast_assignments_{column}", "published_cast_assignments", [column])

    op.create_table(
        "daily_publish_operations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("theater_id", sa.Integer(), nullable=False),
        sa.Column("performance_date", sa.Date(), nullable=False),
        sa.Column("weekly_batch_id", sa.Integer(), nullable=False),
        sa.Column("operator_user_id", sa.Integer(), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_snapshot", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["theater_id"], ["theaters.id"]),
        sa.ForeignKeyConstraint(["weekly_batch_id"], ["weekly_batches.id"]),
        sa.ForeignKeyConstraint(["operator_user_id"], ["users.id"]),
        sa.UniqueConstraint("idempotency_key", name="uq_daily_publish_idempotency_key"),
    )
    for column in ("theater_id", "performance_date", "weekly_batch_id", "operator_user_id"):
        op.create_index(f"ix_daily_publish_operations_{column}", "daily_publish_operations", [column])


def downgrade() -> None:
    op.drop_table("daily_publish_operations")
    op.drop_table("published_cast_assignments")
    op.drop_table("performance_cast_publications")
