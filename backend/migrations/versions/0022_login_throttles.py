"""add login throttles

Revision ID: 0022_login_throttles
Revises: 0021_production_auth_safety
"""

from alembic import op
import sqlalchemy as sa


revision = "0022_login_throttles"
down_revision = "0021_production_auth_safety"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_throttles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("identifier_hash", sa.String(64), nullable=False),
        sa.Column("ip_address", sa.String(64), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_failed_at", sa.DateTime(), nullable=True),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("identifier_hash", "ip_address", name="uq_login_throttle_identity_ip"),
    )
    op.create_index("ix_login_throttles_identifier_hash", "login_throttles", ["identifier_hash"])
    op.create_index("ix_login_throttles_ip_address", "login_throttles", ["ip_address"])


def downgrade() -> None:
    op.drop_table("login_throttles")
