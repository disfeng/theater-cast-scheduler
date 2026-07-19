"""add actor mobile workspace foundation"""

from alembic import op
import sqlalchemy as sa

revision = "0014_actor_mobile_workspace"
down_revision = "0013_top_three_actor_binding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("password_changed_at", sa.DateTime(), nullable=True))
    with op.batch_alter_table("theaters") as batch:
        batch.add_column(sa.Column("reveal_days_before", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("reveal_time", sa.Time(), nullable=False, server_default="21:00:00"))
        batch.add_column(sa.Column("actor_sms_enabled", sa.Boolean(), nullable=False, server_default="0"))
    with op.batch_alter_table("actors") as batch:
        batch.add_column(sa.Column("phone_number", sa.String(length=20), nullable=True))
        batch.create_index("ix_actors_phone_number", ["phone_number"], unique=True)

    op.create_table(
        "actor_theater_memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("actors.id"), nullable=False),
        sa.Column("theater_id", sa.Integer(), sa.ForeignKey("theaters.id"), nullable=False),
        sa.Column("is_entry_theater", sa.Boolean(), nullable=False, server_default="0"),
        sa.UniqueConstraint("actor_id", "theater_id", name="uq_actor_theater_membership"),
    )
    op.create_index("ix_actor_memberships_actor_id", "actor_theater_memberships", ["actor_id"])
    op.create_index("ix_actor_memberships_theater_id", "actor_theater_memberships", ["theater_id"])

    op.create_table(
        "leave_applications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("actors.id"), nullable=False),
        sa.Column("theater_id", sa.Integer(), sa.ForeignKey("theaters.id"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_leave_applications_actor_id", "leave_applications", ["actor_id"])
    op.create_index("ix_leave_applications_theater_id", "leave_applications", ["theater_id"])
    op.create_index("ix_leave_applications_created_at", "leave_applications", ["created_at"])
    op.create_table(
        "leave_application_days",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_id", sa.Integer(), sa.ForeignKey("leave_applications.id"), nullable=False),
        sa.Column("leave_date", sa.Date(), nullable=False),
        sa.Column("status", sa.Enum("PENDING", "APPROVED", "REJECTED", "LOCKED", name="leavestatus"), nullable=False, server_default="PENDING"),
        sa.Column("has_schedule_conflict", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("conflict_performance_ids", sa.JSON(), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("application_id", "leave_date", name="uq_leave_application_day"),
    )
    op.create_index("ix_leave_application_days_application_id", "leave_application_days", ["application_id"])
    op.create_index("ix_leave_application_days_leave_date", "leave_application_days", ["leave_date"])

    op.create_table(
        "actor_notification_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("theater_id", sa.Integer(), sa.ForeignKey("theaters.id"), nullable=False),
        sa.Column("performance_id", sa.Integer(), sa.ForeignKey("performances.id"), nullable=False),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("actors.id"), nullable=False),
        sa.Column("schedule_version", sa.Integer(), nullable=False),
        sa.Column("notification_type", sa.Enum("NEW_ASSIGNMENT", "INFORMATION_UPDATED", "SCHEDULE_CHANGED", "SCHEDULE_CANCELLED", name="actornotificationtype"), nullable=False),
        sa.Column("reveal_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.Enum("PENDING", "REVEALED", "SUPERSEDED", "CANCELLED", name="actornotificationtaskstatus"), nullable=False, server_default="PENDING"),
        sa.Column("assignment_fingerprint", sa.String(length=120), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False, unique=True),
        sa.Column("supersedes_id", sa.Integer(), sa.ForeignKey("actor_notification_tasks.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("revealed_at", sa.DateTime(), nullable=True),
    )
    for column in ("theater_id", "performance_id", "role_id", "actor_id", "reveal_at", "status", "assignment_fingerprint"):
        op.create_index(f"ix_actor_notification_tasks_{column}", "actor_notification_tasks", [column])

    op.create_table(
        "actor_notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("actor_notification_tasks.id"), nullable=True),
        sa.Column("theater_id", sa.Integer(), sa.ForeignKey("theaters.id"), nullable=False),
        sa.Column("performance_id", sa.Integer(), sa.ForeignKey("performances.id"), nullable=False),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("actors.id"), nullable=False),
        sa.Column("notification_type", sa.Enum("NEW_ASSIGNMENT", "INFORMATION_UPDATED", "SCHEDULE_CHANGED", "SCHEDULE_CANCELLED", name="actornotificationtype"), nullable=False),
        sa.Column("schedule_version", sa.Integer(), nullable=False),
        sa.Column("theater_name_snapshot", sa.String(length=120), nullable=False),
        sa.Column("performance_date_snapshot", sa.Date(), nullable=False),
        sa.Column("slot_name_snapshot", sa.String(length=80), nullable=False),
        sa.Column("start_time_snapshot", sa.Time(), nullable=False),
        sa.Column("role_name_snapshot", sa.String(length=120), nullable=False),
        sa.Column("player_name_snapshot", sa.String(length=120), nullable=True),
        sa.Column("designation_type_snapshot", sa.String(length=40), nullable=True),
        sa.Column("idempotency_key", sa.String(length=180), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("read_at", sa.DateTime(), nullable=True),
    )
    for column in ("theater_id", "performance_id", "role_id", "actor_id", "notification_type", "performance_date_snapshot", "created_at"):
        op.create_index(f"ix_actor_notifications_{column}", "actor_notifications", [column])

    op.create_table(
        "sms_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("notification_id", sa.Integer(), sa.ForeignKey("actor_notifications.id"), nullable=False),
        sa.Column("theater_id", sa.Integer(), sa.ForeignKey("theaters.id"), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("actors.id"), nullable=False),
        sa.Column("masked_phone", sa.String(length=30), nullable=False),
        sa.Column("status", sa.Enum("PENDING", "SENDING", "SUCCEEDED", "FAILED", name="smsdeliverystatus"), nullable=False, server_default="PENDING"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("provider_request_id", sa.String(length=120), nullable=True),
        sa.Column("failure_reason", sa.String(length=300), nullable=True),
        sa.Column("idempotency_key", sa.String(length=180), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
    )
    for column in ("notification_id", "theater_id", "actor_id", "status", "next_attempt_at"):
        op.create_index(f"ix_sms_deliveries_{column}", "sms_deliveries", [column])


def downgrade() -> None:
    op.drop_table("sms_deliveries")
    op.drop_table("actor_notifications")
    op.drop_table("actor_notification_tasks")
    op.drop_table("leave_application_days")
    op.drop_table("leave_applications")
    op.drop_table("actor_theater_memberships")
    with op.batch_alter_table("actors") as batch:
        batch.drop_index("ix_actors_phone_number")
        batch.drop_column("phone_number")
    with op.batch_alter_table("theaters") as batch:
        batch.drop_column("actor_sms_enabled")
        batch.drop_column("reveal_time")
        batch.drop_column("reveal_days_before")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("password_changed_at")
        batch.drop_column("must_change_password")
