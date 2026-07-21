"""add scoped administrators and immutable audit logs

Revision ID: 0018_admin_scope_audit
Revises: 0017_entitlement_reversal
"""

from alembic import op
import sqlalchemy as sa


revision = "0018_admin_scope_audit"
down_revision = "0017_entitlement_reversal"
branch_labels = None
depends_on = None


def _replace_user_role_enum(values: str) -> None:
    if op.get_bind().dialect.name == "mysql":
        op.execute(f"ALTER TABLE users MODIFY role ENUM({values}) NOT NULL")


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "mysql":
        _replace_user_role_enum("'ADMIN','ACTOR','SUPER_ADMIN','THEATER_ADMIN'")
    op.execute("UPDATE users SET role = 'SUPER_ADMIN' WHERE role = 'ADMIN'")
    if dialect == "mysql":
        _replace_user_role_enum("'SUPER_ADMIN','THEATER_ADMIN','ACTOR'")

    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("display_name", sa.String(120), nullable=False, server_default="管理员")
        )
        batch.add_column(
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch.add_column(sa.Column("last_login_at", sa.DateTime(), nullable=True))
        batch.create_index("ix_users_is_active", ["is_active"])

    op.create_table(
        "user_theater_scopes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("theater_id", sa.Integer(), nullable=False),
        sa.Column("granted_by_user_id", sa.Integer(), nullable=False),
        sa.Column("granted_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["theater_id"], ["theaters.id"]),
        sa.ForeignKeyConstraint(["granted_by_user_id"], ["users.id"]),
        sa.UniqueConstraint("user_id", "theater_id", name="uq_user_theater_scope"),
    )
    op.create_index("ix_user_theater_scopes_user_id", "user_theater_scopes", ["user_id"])
    op.create_index("ix_user_theater_scopes_theater_id", "user_theater_scopes", ["theater_id"])
    op.create_index(
        "ix_user_theater_scopes_granted_by_user_id",
        "user_theater_scopes",
        ["granted_by_user_id"],
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("operator_user_id", sa.Integer(), nullable=True),
        sa.Column("operator_name_snapshot", sa.String(120), nullable=True),
        sa.Column("operator_role_snapshot", sa.String(40), nullable=True),
        sa.Column("theater_id", sa.Integer(), nullable=True),
        sa.Column(
            "event_category",
            sa.Enum("BUSINESS", "SECURITY", name="auditeventcategory"),
            nullable=False,
        ),
        sa.Column("module", sa.String(60), nullable=False),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("target_type", sa.String(80), nullable=True),
        sa.Column("target_id", sa.String(120), nullable=True),
        sa.Column(
            "result", sa.Enum("SUCCESS", "FAILURE", name="auditresult"), nullable=False
        ),
        sa.Column(
            "risk_level",
            sa.Enum("NORMAL", "WARNING", "CRITICAL", name="auditrisklevel"),
            nullable=False,
        ),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("before_data", sa.JSON(), nullable=True),
        sa.Column("after_data", sa.JSON(), nullable=True),
        sa.Column("affected_objects", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("failure_code", sa.String(120), nullable=True),
        sa.ForeignKeyConstraint(["operator_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["theater_id"], ["theaters.id"]),
    )
    for name, columns in (
        ("ix_audit_logs_occurred_at", ["occurred_at"]),
        ("ix_audit_logs_request_id", ["request_id"]),
        ("ix_audit_logs_operator_user_id", ["operator_user_id"]),
        ("ix_audit_logs_theater_id", ["theater_id"]),
        ("ix_audit_logs_module", ["module"]),
        ("ix_audit_logs_action", ["action"]),
        ("ix_audit_logs_result", ["result"]),
        ("ix_audit_logs_risk_level", ["risk_level"]),
        ("ix_audit_logs_theater_occurred", ["theater_id", "occurred_at"]),
        ("ix_audit_logs_operator_occurred", ["operator_user_id", "occurred_at"]),
        ("ix_audit_logs_module_action", ["module", "action"]),
    ):
        op.create_index(name, "audit_logs", columns)

    if dialect == "sqlite":
        for trigger, operation in (
            ("trg_audit_logs_no_update", "UPDATE"),
            ("trg_audit_logs_no_delete", "DELETE"),
        ):
            op.execute(
                sa.text(
                    f"CREATE TRIGGER {trigger} BEFORE {operation} ON audit_logs "
                    "BEGIN SELECT RAISE(ABORT, 'audit logs are append-only'); END"
                )
            )
    elif dialect == "mysql":
        op.execute(
            "CREATE TRIGGER trg_audit_logs_no_update BEFORE UPDATE ON audit_logs "
            "FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'audit logs are append-only'"
        )
        op.execute(
            "CREATE TRIGGER trg_audit_logs_no_delete BEFORE DELETE ON audit_logs "
            "FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'audit logs are append-only'"
        )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect in {"sqlite", "mysql"}:
        op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_no_update")
        op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_no_delete")
    op.drop_table("audit_logs")
    op.drop_table("user_theater_scopes")
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_is_active")
        batch.drop_column("last_login_at")
        batch.drop_column("is_active")
        batch.drop_column("display_name")
    if dialect == "mysql":
        _replace_user_role_enum("'ADMIN','ACTOR','SUPER_ADMIN','THEATER_ADMIN'")
    op.execute("UPDATE users SET role = 'ADMIN' WHERE role IN ('SUPER_ADMIN','THEATER_ADMIN')")
    if dialect == "mysql":
        _replace_user_role_enum("'ADMIN','ACTOR'")
