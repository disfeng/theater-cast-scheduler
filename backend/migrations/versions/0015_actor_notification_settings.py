"""add actor notification settings

Revision ID: 0015_actor_notification_settings
Revises: 0014_actor_mobile_workspace
"""

from alembic import op
import sqlalchemy as sa

revision = "0015_actor_notification_settings"
down_revision = "0014_actor_mobile_workspace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "actor_notification_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sms_enabled", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("actor_portal_url", sa.String(length=500), nullable=False),
        sa.Column("encrypted_access_key_id", sa.Text(), nullable=True),
        sa.Column("encrypted_access_key_secret", sa.Text(), nullable=True),
        sa.Column("sign_name", sa.String(length=120), nullable=True),
        sa.Column("template_code", sa.String(length=120), nullable=True),
        sa.Column("endpoint", sa.String(length=253), server_default="dysmsapi.aliyuncs.com", nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("actor_notification_settings")
