"""bind top-three entitlement items to ranking actors"""

from alembic import op
import sqlalchemy as sa

revision = "0013_top_three_actor_binding"
down_revision = "0012_theater_entitlements"
branch_labels = None
depends_on = None


TABLES = (
    "entitlement_grant_batches",
    "entitlement_grant_draft_items",
    "entitlement_items",
)


def upgrade() -> None:
    for table in TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("bound_actor_id", sa.Integer(), nullable=True))
            batch.create_index(f"ix_{table}_bound_actor_id", ["bound_actor_id"])
            batch.create_foreign_key(
                f"fk_{table}_bound_actor",
                "actors",
                ["bound_actor_id"],
                ["id"],
            )


def downgrade() -> None:
    for table in reversed(TABLES):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"fk_{table}_bound_actor", type_="foreignkey")
            batch.drop_index(f"ix_{table}_bound_actor_id")
            batch.drop_column("bound_actor_id")
