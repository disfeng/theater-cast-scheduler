"""theater scoped generic entitlement management"""

from alembic import op
import sqlalchemy as sa

revision = "0012_theater_entitlements"
down_revision = "0011_weekly_publish_operations"
branch_labels = None
depends_on = None

LEDGER_TRIGGERS = (
    "trg_entitlement_ledger_entries_no_update",
    "trg_entitlement_ledger_entries_no_delete",
)


def _foreign_keys(enabled: bool) -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "mysql":
        op.execute(sa.text(f"SET FOREIGN_KEY_CHECKS={1 if enabled else 0}"))
    elif dialect == "sqlite":
        op.execute(sa.text(f"PRAGMA foreign_keys={'ON' if enabled else 'OFF'}"))


def _drop_entitlement_tables() -> None:
    for trigger in LEDGER_TRIGGERS:
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger}"))
    for table in (
        "entitlement_ledger_entries",
        "entitlement_items",
        "entitlement_grant_draft_items",
        "entitlement_grant_batches",
        "entitlement_item_types",
    ):
        op.drop_table(table)


def _create_triggers() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        for trigger, operation in zip(LEDGER_TRIGGERS, ("UPDATE", "DELETE"), strict=True):
            op.execute(sa.text(f"CREATE TRIGGER {trigger} BEFORE {operation} ON entitlement_ledger_entries BEGIN SELECT RAISE(ABORT, 'entitlement ledger entries are append-only'); END"))
    elif dialect == "mysql":
        for trigger, operation in zip(LEDGER_TRIGGERS, ("UPDATE", "DELETE"), strict=True):
            op.execute(sa.text(f"CREATE TRIGGER {trigger} BEFORE {operation} ON entitlement_ledger_entries FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'entitlement ledger entries are append-only'"))


def _create_new_tables() -> None:
    op.create_table(
        "entitlement_item_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("theater_id", sa.Integer(), sa.ForeignKey("theaters.id"), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("category", sa.Enum("DESIGNATION", "GENERAL", name="entitlementitemcategory"), nullable=False),
        sa.Column("designation_type", sa.Enum("UNIVERSAL", "TOP_THREE", "PAIRED", name="designationtype", create_type=False), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("default_validity_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("color", sa.String(7), nullable=False, server_default="#409eff"),
        sa.Column("icon", sa.String(80), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("priority >= 0", name="ck_entitlement_item_types_priority_non_negative"),
        sa.CheckConstraint("default_validity_days > 0", name="ck_entitlement_types_validity_positive"),
        sa.CheckConstraint("(category = 'DESIGNATION' AND designation_type IS NOT NULL) OR (category = 'GENERAL' AND designation_type IS NULL)", name="ck_entitlement_types_category_binding"),
        sa.UniqueConstraint("theater_id", "code", name="uq_entitlement_types_theater_code"),
    )
    for column in ("theater_id", "code", "category", "designation_type", "is_active"):
        op.create_index(f"ix_entitlement_item_types_{column}", "entitlement_item_types", [column])

    op.create_table(
        "entitlement_grant_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("theater_id", sa.Integer(), sa.ForeignKey("theaters.id"), nullable=False),
        sa.Column("source_type", sa.Enum("MONTHLY_RANKING", "CAMPAIGN", "REISSUE", "MANUAL_ADJUSTMENT", "OTHER", name="entitlementsourcetype"), nullable=False),
        sa.Column("source_month", sa.Date(), nullable=True),
        sa.Column("source_label", sa.String(120), nullable=False),
        sa.Column("title", sa.String(120), nullable=True),
        sa.Column("grant_date", sa.Date(), nullable=True),
        sa.Column("default_expires_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("confirmed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.Enum("DRAFT", "GRANTED", "CANCELLED", name="grantbatchstatus", create_type=False), nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("granted_at", sa.DateTime(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("idempotency_key", sa.String(120), nullable=True, unique=True),
    )
    for column in ("theater_id", "source_type", "source_month"):
        op.create_index(f"ix_entitlement_grant_batches_{column}", "entitlement_grant_batches", [column])

    op.create_table(
        "entitlement_grant_draft_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("entitlement_grant_batches.id"), nullable=False),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("player_profiles.id"), nullable=False),
        sa.Column("item_type_id", sa.Integer(), sa.ForeignKey("entitlement_item_types.id"), nullable=False),
        sa.Column("source_month", sa.Date(), nullable=True),
        sa.Column("source_label", sa.String(120), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    for column in ("batch_id", "player_id", "item_type_id"):
        op.create_index(f"ix_entitlement_grant_draft_items_{column}", "entitlement_grant_draft_items", [column])

    op.create_table(
        "entitlement_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("theater_id", sa.Integer(), sa.ForeignKey("theaters.id"), nullable=False),
        sa.Column("serial_number", sa.String(80), nullable=False, unique=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("player_profiles.id"), nullable=False),
        sa.Column("item_type_id", sa.Integer(), sa.ForeignKey("entitlement_item_types.id"), nullable=False),
        sa.Column("grant_batch_id", sa.Integer(), sa.ForeignKey("entitlement_grant_batches.id"), nullable=True),
        sa.Column("source_type", sa.Enum("MONTHLY_RANKING", "CAMPAIGN", "REISSUE", "MANUAL_ADJUSTMENT", "OTHER", name="entitlementsourcetype", create_type=False), nullable=False),
        sa.Column("source_month", sa.Date(), nullable=True),
        sa.Column("source_label", sa.String(120), nullable=False),
        sa.Column("granted_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.Enum("AVAILABLE", "RESERVED", "CONSUMED", "EXPIRED", "REVOKED", name="entitlementitemstatus", create_type=False), nullable=False, server_default="AVAILABLE"),
        sa.Column("current_designation_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    for column in ("theater_id", "serial_number", "owner_id", "item_type_id", "grant_batch_id", "source_type", "source_month", "expires_at", "status"):
        op.create_index(f"ix_entitlement_items_{column}", "entitlement_items", [column])

    op.create_table(
        "entitlement_ledger_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("theater_id", sa.Integer(), sa.ForeignKey("theaters.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("entitlement_items.id"), nullable=False),
        sa.Column("event_type", sa.Enum("GRANTED", "RESERVED", "RELEASED", "CONSUMED", "MANUALLY_CONSUMED", "EXPIRED", "REVOKED", "EXTENDED", "RESTORED", "ADJUSTED", name="entitlementeventtype"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("from_status", sa.Enum("AVAILABLE", "RESERVED", "CONSUMED", "EXPIRED", "REVOKED", name="entitlementitemstatus", create_type=False), nullable=True),
        sa.Column("to_status", sa.Enum("AVAILABLE", "RESERVED", "CONSUMED", "EXPIRED", "REVOKED", name="entitlementitemstatus", create_type=False), nullable=True),
        sa.Column("performance_id", sa.Integer(), sa.ForeignKey("performances.id"), nullable=True),
        sa.Column("designation_id", sa.Integer(), sa.ForeignKey("designations.id"), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("purpose", sa.String(200), nullable=True),
        sa.Column("operator_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    for column in ("theater_id", "item_id", "event_type", "occurred_at"):
        op.create_index(f"ix_entitlement_ledger_entries_{column}", "entitlement_ledger_entries", [column])
    _create_triggers()


def upgrade() -> None:
    _foreign_keys(False)
    _drop_entitlement_tables()
    _create_new_tables()
    _foreign_keys(True)


def downgrade() -> None:
    # Entitlement data is intentionally disposable for this pre-production feature.
    _foreign_keys(False)
    _drop_entitlement_tables()
    # Reuse the original migration contract by rebuilding through a downgrade/upgrade cycle.
    op.create_table(
        "entitlement_item_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("default_validity_months", sa.Integer(), nullable=False),
    )
    op.create_table(
        "entitlement_grant_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_month", sa.Date(), nullable=False),
        sa.Column("source_label", sa.String(120), nullable=False),
        sa.Column("title", sa.String(120)), sa.Column("grant_date", sa.Date()), sa.Column("default_expires_at", sa.DateTime()), sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id")), sa.Column("confirmed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("status", sa.Enum("DRAFT", "GRANTED", "CANCELLED", name="grantbatchstatus", create_type=False), nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()), sa.Column("granted_at", sa.DateTime()), sa.Column("confirmed_at", sa.DateTime()),
    )
    op.create_table("entitlement_grant_draft_items", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("batch_id", sa.Integer(), sa.ForeignKey("entitlement_grant_batches.id"), nullable=False), sa.Column("player_id", sa.Integer(), sa.ForeignKey("player_profiles.id"), nullable=False), sa.Column("item_type_id", sa.Integer(), sa.ForeignKey("entitlement_item_types.id"), nullable=False), sa.Column("source_month", sa.Date()), sa.Column("source_label", sa.String(120)), sa.Column("expires_at", sa.DateTime()), sa.Column("notes", sa.Text()))
    op.create_table("entitlement_items", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("serial_number", sa.String(80), nullable=False, unique=True), sa.Column("owner_id", sa.Integer(), sa.ForeignKey("player_profiles.id"), nullable=False), sa.Column("item_type_id", sa.Integer(), sa.ForeignKey("entitlement_item_types.id"), nullable=False), sa.Column("grant_batch_id", sa.Integer(), sa.ForeignKey("entitlement_grant_batches.id")), sa.Column("source_month", sa.Date(), nullable=False), sa.Column("source_label", sa.String(120), nullable=False), sa.Column("granted_at", sa.DateTime(), nullable=False), sa.Column("expires_at", sa.DateTime(), nullable=False), sa.Column("status", sa.Enum("AVAILABLE", "RESERVED", "CONSUMED", "EXPIRED", "REVOKED", name="entitlementitemstatus", create_type=False), nullable=False, server_default="AVAILABLE"), sa.Column("current_designation_id", sa.Integer()), sa.Column("notes", sa.Text()))
    op.create_table("entitlement_ledger_entries", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("item_id", sa.Integer(), sa.ForeignKey("entitlement_items.id"), nullable=False), sa.Column("event_type", sa.Enum("GRANTED", "RESERVED", "RELEASED", "CONSUMED", "EXPIRED", "REVOKED", "EXTENDED", "RESTORED", "ADJUSTED", name="entitlementeventtype"), nullable=False), sa.Column("occurred_at", sa.DateTime(), nullable=False, server_default=sa.func.now()), sa.Column("note", sa.Text()), sa.Column("from_status", sa.Enum("AVAILABLE", "RESERVED", "CONSUMED", "EXPIRED", "REVOKED", name="entitlementitemstatus", create_type=False)), sa.Column("to_status", sa.Enum("AVAILABLE", "RESERVED", "CONSUMED", "EXPIRED", "REVOKED", name="entitlementitemstatus", create_type=False)), sa.Column("performance_id", sa.Integer()), sa.Column("designation_id", sa.Integer()), sa.Column("reason", sa.Text()), sa.Column("operator_user_id", sa.Integer(), sa.ForeignKey("users.id")))
    _create_triggers()
    _foreign_keys(True)
