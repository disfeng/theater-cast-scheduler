"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-12
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "theaters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("default_weekly_template", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("group_name", sa.String(length=120), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="name"),
    )
    op.create_table(
        "actors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("max_consecutive_performances", sa.Integer(), nullable=False),
        sa.Column(
            "rating_level",
            sa.Enum("HIGH", "NORMAL", "LOW", "SUSPENDED", name="ratinglevel"),
            nullable=False,
        ),
        sa.Column("low_rating_monthly_cap", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("display_name"),
    )
    op.create_index(op.f("ix_actors_display_name"), "actors", ["display_name"], unique=False)
    op.create_table(
        "performances",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("theater_id", sa.Integer(), nullable=False),
        sa.Column("performance_date", sa.Date(), nullable=False),
        sa.Column("slot", sa.String(length=20), nullable=False),
        sa.Column(
            "status",
            sa.Enum("DRAFT", "SCHEDULED", "PUBLISHED", "CANCELLED", name="performancestatus"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["theater_id"], ["theaters.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_performances_performance_date"), "performances", ["performance_date"], unique=False
    )
    op.create_index(op.f("ix_performances_slot"), "performances", ["slot"], unique=False)
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.Enum("ADMIN", "ACTOR", name="userrole"), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=False)
    op.create_index(op.f("ix_users_role"), "users", ["role"], unique=False)
    op.create_table(
        "actor_role_capabilities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("actor_id", "role_id"),
    )
    op.create_table(
        "leave_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("leave_date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "APPROVED", "REJECTED", "LOCKED", name="leavestatus"),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("actor_id", "leave_date"),
    )
    op.create_index(
        op.f("ix_leave_requests_actor_id"), "leave_requests", ["actor_id"], unique=False
    )
    op.create_index(
        op.f("ix_leave_requests_leave_date"), "leave_requests", ["leave_date"], unique=False
    )
    op.create_table(
        "designations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "designation_type",
            sa.Enum("UNIVERSAL", "TOP_THREE", "PAIRED", name="designationtype"),
            nullable=False,
        ),
        sa.Column("player_name", sa.String(length=120), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("target_performance_id", sa.Integer(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.Column("included_in_batch", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.ForeignKeyConstraint(["target_performance_id"], ["performances.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_designations_designation_type"), "designations", ["designation_type"], unique=False
    )
    op.create_index(
        op.f("ix_designations_submitted_at"), "designations", ["submitted_at"], unique=False
    )
    op.create_table(
        "wishes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("player_name", sa.String(length=120), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "schedule_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("performance_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("locked", sa.Boolean(), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"]),
        sa.ForeignKeyConstraint(["performance_id"], ["performances.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("performance_id", "role_id"),
    )
    op.create_index(
        op.f("ix_schedule_assignments_actor_id"), "schedule_assignments", ["actor_id"], unique=False
    )
    op.create_index(
        op.f("ix_schedule_assignments_performance_id"),
        "schedule_assignments",
        ["performance_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_schedule_assignments_role_id"), "schedule_assignments", ["role_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_schedule_assignments_role_id"), table_name="schedule_assignments")
    op.drop_index(op.f("ix_schedule_assignments_performance_id"), table_name="schedule_assignments")
    op.drop_index(op.f("ix_schedule_assignments_actor_id"), table_name="schedule_assignments")
    op.drop_table("schedule_assignments")
    op.drop_table("wishes")
    op.drop_index(op.f("ix_designations_submitted_at"), table_name="designations")
    op.drop_index(op.f("ix_designations_designation_type"), table_name="designations")
    op.drop_table("designations")
    op.drop_index(op.f("ix_leave_requests_leave_date"), table_name="leave_requests")
    op.drop_index(op.f("ix_leave_requests_actor_id"), table_name="leave_requests")
    op.drop_table("leave_requests")
    op.drop_table("actor_role_capabilities")
    op.drop_index(op.f("ix_users_role"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
    op.drop_index(op.f("ix_performances_slot"), table_name="performances")
    op.drop_index(op.f("ix_performances_performance_date"), table_name="performances")
    op.drop_table("performances")
    op.drop_index(op.f("ix_actors_display_name"), table_name="actors")
    op.drop_table("actors")
    op.drop_table("roles")
    op.drop_table("theaters")
