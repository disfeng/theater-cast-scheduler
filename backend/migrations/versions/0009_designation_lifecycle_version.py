"""add designation lifecycle optimistic-lock version

Revision ID: 0009_designation_lifecycle
Revises: 0008_ai_parser_settings
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_designation_lifecycle"
down_revision = "0008_ai_parser_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    designation_columns = {column["name"] for column in inspector.get_columns("designations")}
    if "version" not in designation_columns:
        op.add_column(
            "designations", sa.Column("version", sa.Integer(), server_default="1", nullable=False)
        )
    op.execute(
        "UPDATE designations SET lifecycle_status = CASE WHEN status = 'confirmed' THEN 'legacy_review_required' ELSE 'draft' END WHERE lifecycle_status IS NULL"
    )
    op.execute(
        "UPDATE designations SET verification_status = 'not_required' WHERE verification_status IS NULL"
    )
    op.execute("UPDATE designations SET usage_type = 'self' WHERE usage_type IS NULL")
    if "designation_lifecycle_events" not in inspector.get_table_names():
        op.create_table(
            "designation_lifecycle_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "designation_id", sa.Integer(), sa.ForeignKey("designations.id"), nullable=False
            ),
            sa.Column("operator_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("action", sa.String(40), nullable=False),
            sa.Column("idempotency_key", sa.String(120), nullable=False),
            sa.Column("request_hash", sa.String(64), nullable=False),
            sa.Column("result_snapshot", sa.JSON(), nullable=False),
            sa.Column("from_status", sa.String(40)),
            sa.Column("to_status", sa.String(40)),
            sa.Column("entitlement_item_id", sa.Integer(), sa.ForeignKey("entitlement_items.id")),
            sa.Column("conflict_designation_id", sa.Integer(), sa.ForeignKey("designations.id")),
            sa.Column("note", sa.Text()),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint(
                "designation_id",
                "action",
                "idempotency_key",
                name="uq_designation_action_idempotency",
            ),
        )
        op.create_index(
            "ix_designation_lifecycle_events_designation_id",
            "designation_lifecycle_events",
            ["designation_id"],
        )
    else:
        lifecycle_indexes = {
            index["name"] for index in sa.inspect(bind).get_indexes("designation_lifecycle_events")
        }
        if "ix_designation_lifecycle_events_designation_id" not in lifecycle_indexes:
            op.create_index(
                "ix_designation_lifecycle_events_designation_id",
                "designation_lifecycle_events",
                ["designation_id"],
            )


def downgrade() -> None:
    op.drop_index(
        "ix_designation_lifecycle_events_designation_id", table_name="designation_lifecycle_events"
    )
    op.drop_table("designation_lifecycle_events")
    op.drop_column("designations", "version")
