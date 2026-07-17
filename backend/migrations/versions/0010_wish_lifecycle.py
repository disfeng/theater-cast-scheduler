"""wish lifecycle concurrency and audit"""

from alembic import op
import sqlalchemy as sa
import hashlib

revision = "0010_wish_lifecycle"
down_revision = "0009_designation_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("wishes") as batch:
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("active_scope_key", sa.String(64), nullable=True))
    bind = op.get_bind()
    # Legacy weekly wishes lack a concrete performance/player scope. Keep them readable,
    # but classify them explicitly so current APIs never treat them as active wishes.
    bind.execute(sa.text("UPDATE wishes SET status='legacy_review_required' WHERE status IS NULL"))
    rows = bind.execute(
        sa.text(
            "SELECT id, performance_id, performance_player_id, actor_id, role_id FROM wishes WHERE status = 'active' AND performance_id IS NOT NULL AND performance_player_id IS NOT NULL ORDER BY id"
        )
    ).mappings()
    seen = set()
    for row in rows:
        key = hashlib.sha256(
            f"{row['performance_id']}:{row['performance_player_id']}:{row['actor_id']}:{row['role_id']}".encode()
        ).hexdigest()
        if key in seen:
            bind.execute(
                sa.text(
                    "UPDATE wishes SET status='cancelled', failure_reason='migration_duplicate_active_wish', version=version+1 WHERE id=:id"
                ),
                {"id": row["id"]},
            )
        else:
            seen.add(key)
            bind.execute(
                sa.text("UPDATE wishes SET active_scope_key=:key WHERE id=:id"),
                {"key": key, "id": row["id"]},
            )
    with op.batch_alter_table("wishes") as batch:
        batch.create_unique_constraint("uq_wish_active_scope_key", ["active_scope_key"])
    op.create_table(
        "wish_lifecycle_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("wish_id", sa.Integer(), sa.ForeignKey("wishes.id"), nullable=False),
        sa.Column("operator_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("result_snapshot", sa.JSON(), nullable=False),
        sa.Column("from_status", sa.String(40)),
        sa.Column("to_status", sa.String(40)),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("action", "idempotency_key", name="uq_wish_action_idempotency"),
    )
    op.create_index("ix_wish_lifecycle_events_wish_id", "wish_lifecycle_events", ["wish_id"])
    op.create_index(
        "ix_wish_lifecycle_events_operator_user_id", "wish_lifecycle_events", ["operator_user_id"]
    )


def downgrade():
    op.drop_table("wish_lifecycle_events")
    with op.batch_alter_table("wishes") as batch:
        batch.drop_constraint("uq_wish_active_scope_key", type_="unique")
        batch.drop_column("active_scope_key")
        batch.drop_column("version")
