"""global encrypted ai parser settings"""

from alembic import op
import sqlalchemy as sa

revision = "0008_ai_parser_settings"
down_revision = "0007_performance_boards"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_parser_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("endpoint", sa.String(500), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=True),
        sa.Column("model_name", sa.String(120), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("prompt_version", sa.String(80), nullable=False),
        sa.Column("last_test_ok", sa.Boolean(), nullable=True),
        sa.Column("last_test_message", sa.String(200), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "ai_parser_settings_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True
        ),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("changed_fields", sa.JSON(), nullable=True),
        sa.Column("key_replaced", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("provider_host", sa.String(253), nullable=True),
        sa.Column("model_name", sa.String(120), nullable=True),
        sa.Column("outcome", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("ai_parser_settings_audit")
    op.drop_table("ai_parser_settings")
