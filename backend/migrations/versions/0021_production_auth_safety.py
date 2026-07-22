"""add production authentication safety state

Revision ID: 0021_production_auth_safety
Revises: 0020_entitlement_bindings
"""

from alembic import op
import sqlalchemy as sa


revision = "0021_production_auth_safety"
down_revision = "0020_entitlement_bindings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("last_failed_login_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("locked_until", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("locked_until")
        batch.drop_column("last_failed_login_at")
        batch.drop_column("failed_login_count")
        batch.drop_column("token_version")
