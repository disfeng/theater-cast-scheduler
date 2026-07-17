"""add player identity and entitlement inventory

Revision ID: 0006_entitlement_inventory
Revises: 0005_weekly_scheduling_workspace
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_entitlement_inventory"
down_revision: str | None = "0005_weekly_scheduling_workspace"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEDGER_NO_UPDATE_TRIGGER = "trg_entitlement_ledger_entries_no_update"
LEDGER_NO_DELETE_TRIGGER = "trg_entitlement_ledger_entries_no_delete"
LEDGER_IMMUTABLE_MESSAGE = "entitlement ledger entries are append-only"


def _create_ledger_immutability_triggers() -> None:
    dialect_name = op.get_bind().dialect.name
    if dialect_name == "sqlite":
        for trigger_name, operation in (
            (LEDGER_NO_UPDATE_TRIGGER, "UPDATE"),
            (LEDGER_NO_DELETE_TRIGGER, "DELETE"),
        ):
            op.execute(
                sa.text(
                    f"CREATE TRIGGER {trigger_name} BEFORE {operation} "
                    "ON entitlement_ledger_entries BEGIN "
                    f"SELECT RAISE(ABORT, '{LEDGER_IMMUTABLE_MESSAGE}'); END"
                )
            )
    elif dialect_name == "mysql":
        for trigger_name, operation in (
            (LEDGER_NO_UPDATE_TRIGGER, "UPDATE"),
            (LEDGER_NO_DELETE_TRIGGER, "DELETE"),
        ):
            op.execute(
                sa.text(
                    f"CREATE TRIGGER {trigger_name} BEFORE {operation} "
                    "ON entitlement_ledger_entries FOR EACH ROW "
                    f"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '{LEDGER_IMMUTABLE_MESSAGE}'"
                )
            )


def _drop_ledger_immutability_triggers() -> None:
    for trigger_name in (LEDGER_NO_UPDATE_TRIGGER, LEDGER_NO_DELETE_TRIGGER):
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger_name}"))


def upgrade() -> None:
    op.create_table(
        "player_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("normalized_name", sa.String(length=120), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PROVISIONAL", "ACTIVE", "INACTIVE", "MERGED", name="playerstatus"),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "merged_into_id", sa.Integer(), sa.ForeignKey("player_profiles.id"), nullable=True
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.UniqueConstraint("normalized_name"),
    )
    op.create_index("ix_player_profiles_normalized_name", "player_profiles", ["normalized_name"])

    op.create_table(
        "player_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("player_profiles.id"), nullable=False),
        sa.Column("alias", sa.String(length=120), nullable=False),
        sa.Column("normalized_alias", sa.String(length=120), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("normalized_alias"),
    )
    op.create_index("ix_player_aliases_player_id", "player_aliases", ["player_id"])
    op.create_index("ix_player_aliases_normalized_alias", "player_aliases", ["normalized_alias"])

    item_types = op.create_table(
        "entitlement_item_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("default_validity_months", sa.Integer(), nullable=False),
        sa.CheckConstraint("priority >= 0", name="ck_entitlement_item_types_priority_non_negative"),
        sa.CheckConstraint(
            "default_validity_months > 0",
            name="ck_entitlement_item_types_validity_months_positive",
        ),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_entitlement_item_types_code", "entitlement_item_types", ["code"])
    op.bulk_insert(
        item_types,
        [
            {
                "code": "universal",
                "display_name": "万能指定",
                "priority": 1,
                "default_validity_months": 3,
            },
            {
                "code": "top_three",
                "display_name": "榜单前三指定",
                "priority": 2,
                "default_validity_months": 3,
            },
            {
                "code": "paired",
                "display_name": "对位指定",
                "priority": 3,
                "default_validity_months": 3,
            },
        ],
    )

    op.create_table(
        "entitlement_grant_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_month", sa.Date(), nullable=False),
        sa.Column("source_label", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=True),
        sa.Column("grant_date", sa.Date(), nullable=True),
        sa.Column("default_expires_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("confirmed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "status",
            sa.Enum("DRAFT", "GRANTED", "CANCELLED", name="grantbatchstatus"),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("granted_at", sa.DateTime(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_entitlement_grant_batches_source_month", "entitlement_grant_batches", ["source_month"]
    )

    op.create_table(
        "entitlement_grant_draft_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "batch_id", sa.Integer(), sa.ForeignKey("entitlement_grant_batches.id"), nullable=False
        ),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("player_profiles.id"), nullable=False),
        sa.Column(
            "item_type_id", sa.Integer(), sa.ForeignKey("entitlement_item_types.id"), nullable=False
        ),
        sa.Column("source_month", sa.Date(), nullable=True),
        sa.Column("source_label", sa.String(length=120), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    for column in ("batch_id", "player_id", "item_type_id"):
        op.create_index(
            f"ix_entitlement_grant_draft_items_{column}", "entitlement_grant_draft_items", [column]
        )

    op.create_table(
        "entitlement_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("serial_number", sa.String(length=80), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("player_profiles.id"), nullable=False),
        sa.Column(
            "item_type_id", sa.Integer(), sa.ForeignKey("entitlement_item_types.id"), nullable=False
        ),
        sa.Column(
            "grant_batch_id",
            sa.Integer(),
            sa.ForeignKey("entitlement_grant_batches.id"),
            nullable=True,
        ),
        sa.Column("source_month", sa.Date(), nullable=False),
        sa.Column("source_label", sa.String(length=120), nullable=False),
        sa.Column("granted_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "AVAILABLE",
                "RESERVED",
                "CONSUMED",
                "EXPIRED",
                "REVOKED",
                name="entitlementitemstatus",
            ),
            nullable=False,
            server_default="AVAILABLE",
        ),
        sa.Column("current_designation_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.UniqueConstraint("serial_number"),
    )
    for column in (
        "serial_number",
        "owner_id",
        "item_type_id",
        "grant_batch_id",
        "source_month",
        "expires_at",
        "status",
    ):
        op.create_index(f"ix_entitlement_items_{column}", "entitlement_items", [column])

    op.create_table(
        "entitlement_ledger_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("entitlement_items.id"), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "GRANTED",
                "RESERVED",
                "RELEASED",
                "CONSUMED",
                "EXPIRED",
                "REVOKED",
                "EXTENDED",
                "RESTORED",
                "ADJUSTED",
                name="entitlementeventtype",
            ),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "from_status",
            sa.Enum(
                "AVAILABLE",
                "RESERVED",
                "CONSUMED",
                "EXPIRED",
                "REVOKED",
                name="entitlementitemstatus",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "to_status",
            sa.Enum(
                "AVAILABLE",
                "RESERVED",
                "CONSUMED",
                "EXPIRED",
                "REVOKED",
                name="entitlementitemstatus",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("performance_id", sa.Integer(), nullable=True),
        sa.Column("designation_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("operator_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    for column in ("item_id", "event_type", "occurred_at"):
        op.create_index(
            f"ix_entitlement_ledger_entries_{column}", "entitlement_ledger_entries", [column]
        )
    _create_ledger_immutability_triggers()


def downgrade() -> None:
    _drop_ledger_immutability_triggers()
    op.execute(sa.text("DELETE FROM entitlement_ledger_entries"))
    op.execute(sa.text("DELETE FROM entitlement_items"))
    op.execute(
        sa.text(
            "DELETE FROM entitlement_item_types WHERE code IN ('universal', 'top_three', 'paired')"
        )
    )
    op.drop_table("entitlement_ledger_entries")
    op.drop_table("entitlement_items")
    op.drop_table("entitlement_grant_draft_items")
    op.drop_table("entitlement_grant_batches")
    op.drop_table("player_aliases")
    op.drop_table("entitlement_item_types")
    op.drop_table("player_profiles")
