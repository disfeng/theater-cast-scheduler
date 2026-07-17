"""durable weekly publish operations"""

from alembic import op
import sqlalchemy as sa

revision = "0011_weekly_publish_operations"
down_revision = "0010_wish_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "weekly_publish_operations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("theater_id", sa.Integer(), sa.ForeignKey("theaters.id"), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column(
            "weekly_batch_id", sa.Integer(), sa.ForeignKey("weekly_batches.id"), nullable=True
        ),
        sa.Column("operator_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("confirmation_token", sa.String(120), nullable=True),
        sa.Column("unmet_scope_hash", sa.String(64), nullable=True),
        sa.Column("unmet_scope", sa.JSON(), nullable=True),
        sa.Column("response_snapshot", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("idempotency_key", name="uq_weekly_publish_idempotency_key"),
        sa.UniqueConstraint("confirmation_token", name="uq_weekly_publish_confirmation_token"),
    )
    op.create_index(
        "ix_weekly_publish_operations_theater_id", "weekly_publish_operations", ["theater_id"]
    )
    op.create_index(
        "ix_weekly_publish_operations_week_start", "weekly_publish_operations", ["week_start"]
    )
    op.create_index(
        "ix_weekly_publish_operations_weekly_batch_id",
        "weekly_publish_operations",
        ["weekly_batch_id"],
    )
    op.create_index(
        "ix_weekly_publish_operations_operator_user_id",
        "weekly_publish_operations",
        ["operator_user_id"],
    )


def downgrade():
    op.drop_table("weekly_publish_operations")
