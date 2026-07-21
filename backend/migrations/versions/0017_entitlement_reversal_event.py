"""add entitlement reversal event

Revision ID: 0017_entitlement_reversal
Revises: 0016_fulfillment_corrections
"""

from alembic import op


revision = "0017_entitlement_reversal"
down_revision = "0016_fulfillment_corrections"
branch_labels = None
depends_on = None


VALUES = (
    "'GRANTED','RESERVED','RELEASED','CONSUMED','MANUALLY_CONSUMED',"
    "'EXPIRED','REVOKED','EXTENDED','RESTORED','ADJUSTED','REVERSED'"
)
OLD_VALUES = (
    "'GRANTED','RESERVED','RELEASED','CONSUMED','MANUALLY_CONSUMED',"
    "'EXPIRED','REVOKED','EXTENDED','RESTORED','ADJUSTED'"
)


def upgrade() -> None:
    if op.get_bind().dialect.name != "mysql":
        return
    op.execute(
        f"ALTER TABLE entitlement_ledger_entries MODIFY event_type ENUM({VALUES}) NOT NULL"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "mysql":
        return
    op.execute("DELETE FROM entitlement_ledger_entries WHERE event_type = 'REVERSED'")
    op.execute(
        f"ALTER TABLE entitlement_ledger_entries MODIFY event_type ENUM({OLD_VALUES}) NOT NULL"
    )
