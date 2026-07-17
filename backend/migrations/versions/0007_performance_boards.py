"""add performance-scoped versioned information boards

Revision ID: 0007_performance_boards
Revises: 0006_entitlement_inventory
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_performance_boards"
down_revision: str | None = "0006_entitlement_inventory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "performance_boards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("performance_id", sa.Integer(), sa.ForeignKey("performances.id"), nullable=False),
        sa.Column("current_revision_id", sa.Integer(), nullable=True),
        sa.Column("next_revision_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("performance_id"),
        sa.UniqueConstraint("performance_id", "id", name="uq_performance_board_scope"),
    )
    op.create_index(
        "ix_performance_boards_performance_id", "performance_boards", ["performance_id"]
    )
    op.create_table(
        "performance_board_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("board_id", sa.Integer(), sa.ForeignKey("performance_boards.id"), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("REVIEW_REQUIRED", "CONFIRMED", "FAILED", name="boardrevisionstatus"),
            nullable=False,
            server_default="REVIEW_REQUIRED",
        ),
        sa.Column(
            "parser_type",
            sa.Enum("DETERMINISTIC", "AI", name="boardparsertype"),
            nullable=False,
            server_default="DETERMINISTIC",
        ),
        sa.Column("provider_name", sa.String(120), nullable=True),
        sa.Column("model_name", sa.String(120), nullable=True),
        sa.Column("prompt_version", sa.String(80), nullable=True),
        sa.Column("raw_ai_response", sa.Text(), nullable=True),
        sa.Column("parsed_payload", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "rollback_source_revision_id",
            sa.Integer(),
            sa.ForeignKey("performance_board_revisions.id"),
            nullable=True,
        ),
        sa.UniqueConstraint("board_id", "revision_number", name="uq_board_revision_number"),
        sa.UniqueConstraint("board_id", "id", name="uq_board_revision_scope"),
    )
    op.create_index(
        "ix_performance_board_revisions_board_id", "performance_board_revisions", ["board_id"]
    )
    with op.batch_alter_table("performance_boards") as batch:
        batch.create_foreign_key(
            "fk_performance_boards_current_revision_scope",
            "performance_board_revisions",
            ["id", "current_revision_id"],
            ["board_id", "id"],
        )
    op.create_table(
        "performance_players",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("performance_id", sa.Integer(), sa.ForeignKey("performances.id"), nullable=False),
        sa.Column(
            "player_profile_id", sa.Integer(), sa.ForeignKey("player_profiles.id"), nullable=True
        ),
        sa.Column("player_name_snapshot", sa.String(120), nullable=False),
        sa.Column("player_character_name", sa.String(120), nullable=False),
        sa.Column("paired_role_name", sa.String(120), nullable=False),
        sa.Column("relation_label", sa.String(80), nullable=True),
        sa.Column("theater_visit_ordinal", sa.Integer(), nullable=True),
        sa.Column("character_visit_ordinal", sa.Integer(), nullable=True),
        sa.Column("source_board_id", sa.Integer(), nullable=False),
        sa.Column("source_revision_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint(
            "performance_id", "player_character_name", name="uq_performance_player_character"
        ),
        sa.ForeignKeyConstraint(
            ["performance_id", "source_board_id"],
            ["performance_boards.performance_id", "performance_boards.id"],
            name="fk_performance_players_board_scope",
        ),
        sa.ForeignKeyConstraint(
            ["source_board_id", "source_revision_id"],
            ["performance_board_revisions.board_id", "performance_board_revisions.id"],
            name="fk_performance_players_revision_scope",
        ),
    )
    op.create_index(
        "ix_performance_players_performance_id", "performance_players", ["performance_id"]
    )
    op.create_table(
        "board_draft_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "revision_id",
            sa.Integer(),
            sa.ForeignKey("performance_board_revisions.id"),
            nullable=False,
        ),
        sa.Column(
            "item_kind",
            sa.Enum("PLAYER", "DESIGNATION", "WISH", "UNRESOLVED", name="boarditemkind"),
            nullable=False,
        ),
        sa.Column(
            "change_type",
            sa.Enum("ADDED", "MODIFIED", "UNCHANGED", "REMOVED", name="boardchangetype"),
            nullable=False,
        ),
        sa.Column("stable_key", sa.String(300), nullable=False),
        sa.Column("raw_line", sa.Text(), nullable=True),
        sa.Column("player_name", sa.String(120), nullable=True),
        sa.Column("player_character_name", sa.String(120), nullable=True),
        sa.Column("paired_role_name", sa.String(120), nullable=True),
        sa.Column("relation_label", sa.String(80), nullable=True),
        sa.Column("theater_visit_ordinal", sa.Integer(), nullable=True),
        sa.Column("character_visit_ordinal", sa.Integer(), nullable=True),
        sa.Column("actor_name_raw", sa.String(120), nullable=True),
        sa.Column("role_name_raw", sa.String(120), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "matched_player_id", sa.Integer(), sa.ForeignKey("player_profiles.id"), nullable=True
        ),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("actors.id"), nullable=True),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id"), nullable=True),
        sa.Column("candidates", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.JSON(), nullable=True),
        sa.Column(
            "validation_status",
            sa.Enum("VALID", "AMBIGUOUS", "INVALID", name="boardvalidationstatus"),
            nullable=False,
            server_default="VALID",
        ),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("confirmed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "performance_player_id",
            sa.Integer(),
            sa.ForeignKey("performance_players.id"),
            nullable=True,
        ),
        sa.Column("designation_id", sa.Integer(), sa.ForeignKey("designations.id"), nullable=True),
        sa.Column("wish_id", sa.Integer(), sa.ForeignKey("wishes.id"), nullable=True),
        sa.Column(
            "removal_lifecycle_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.UniqueConstraint("revision_id", "stable_key", name="uq_board_draft_revision_stable_key"),
    )
    op.create_index("ix_board_draft_items_revision_id", "board_draft_items", ["revision_id"])
    op.create_index("ix_board_draft_items_stable_key", "board_draft_items", ["stable_key"])

    designation_columns = (
        sa.Column("performance_id", sa.Integer(), nullable=True),
        sa.Column("beneficiary_performance_player_id", sa.Integer(), nullable=True),
        sa.Column("owner_player_id", sa.Integer(), nullable=True),
        sa.Column("entitlement_item_id", sa.Integer(), nullable=True),
        sa.Column("usage_type", sa.String(40), nullable=True),
        sa.Column("verification_status", sa.String(40), nullable=True),
        sa.Column("verified_by", sa.Integer(), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("verification_note", sa.Text(), nullable=True),
        sa.Column("lifecycle_status", sa.String(40), nullable=True),
        sa.Column("replaced_designation_id", sa.Integer(), nullable=True),
    )
    with op.batch_alter_table("designations") as batch:
        for column in designation_columns:
            batch.add_column(column)
        batch.create_foreign_key(
            "fk_designations_performance", "performances", ["performance_id"], ["id"]
        )
        batch.create_foreign_key(
            "fk_designations_beneficiary_performance_player",
            "performance_players",
            ["beneficiary_performance_player_id"],
            ["id"],
        )
        batch.create_foreign_key(
            "fk_designations_owner_player", "player_profiles", ["owner_player_id"], ["id"]
        )
        batch.create_foreign_key(
            "fk_designations_entitlement_item", "entitlement_items", ["entitlement_item_id"], ["id"]
        )
        batch.create_foreign_key("fk_designations_verified_by", "users", ["verified_by"], ["id"])
        batch.create_foreign_key(
            "fk_designations_replaced_designation",
            "designations",
            ["replaced_designation_id"],
            ["id"],
        )
    with op.batch_alter_table("wishes") as batch:
        batch.add_column(sa.Column("performance_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("performance_player_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("status", sa.String(40), nullable=True))
        batch.add_column(sa.Column("failure_reason", sa.Text(), nullable=True))
        batch.create_foreign_key(
            "fk_wishes_performance", "performances", ["performance_id"], ["id"]
        )
        batch.create_foreign_key(
            "fk_wishes_performance_player",
            "performance_players",
            ["performance_player_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("wishes") as batch:
        batch.drop_constraint("fk_wishes_performance_player", type_="foreignkey")
        batch.drop_constraint("fk_wishes_performance", type_="foreignkey")
        for name in ("failure_reason", "status", "performance_player_id", "performance_id"):
            batch.drop_column(name)
    with op.batch_alter_table("designations") as batch:
        for name in (
            "fk_designations_replaced_designation",
            "fk_designations_verified_by",
            "fk_designations_entitlement_item",
            "fk_designations_owner_player",
            "fk_designations_beneficiary_performance_player",
            "fk_designations_performance",
        ):
            batch.drop_constraint(name, type_="foreignkey")
        for name in (
            "replaced_designation_id",
            "lifecycle_status",
            "verification_note",
            "verified_at",
            "verified_by",
            "verification_status",
            "usage_type",
            "entitlement_item_id",
            "owner_player_id",
            "beneficiary_performance_player_id",
            "performance_id",
        ):
            batch.drop_column(name)
    op.drop_table("board_draft_items")
    op.drop_table("performance_players")
    with op.batch_alter_table("performance_boards") as batch:
        batch.drop_constraint("fk_performance_boards_current_revision_scope", type_="foreignkey")
    op.drop_table("performance_board_revisions")
    op.drop_table("performance_boards")
