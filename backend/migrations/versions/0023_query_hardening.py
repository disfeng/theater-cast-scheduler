"""add high-frequency query indexes

Revision ID: 0023_query_hardening
Revises: 0022_login_throttles
"""

from alembic import op


revision = "0023_query_hardening"
down_revision = "0022_login_throttles"
branch_labels = None
depends_on = None


INDEXES = (
    ("ix_performances_theater_date_status", "performances", ["theater_id", "performance_date", "status"]),
    ("ix_entitlement_items_theater_owner_status", "entitlement_items", ["theater_id", "owner_id", "status"]),
    ("ix_entitlement_items_theater_type_status_expiry", "entitlement_items", ["theater_id", "item_type_id", "status", "expires_at"]),
    ("ix_entitlement_ledger_theater_id", "entitlement_ledger_entries", ["theater_id", "id"]),
    ("ix_leave_days_status_date", "leave_application_days", ["status", "leave_date", "withdrawn_at"]),
    ("ix_schedule_assignments_actor_performance", "schedule_assignments", ["actor_id", "performance_id"]),
)


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table)
