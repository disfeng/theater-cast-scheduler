from logging.config import fileConfig

from alembic import context
import sqlalchemy as sa
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.db.base import Base
from app.models import entities  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

STRING_BACKED_ENUM_COLUMNS = {
    ("import_draft_items", "item_kind"),
    ("import_draft_items", "designation_type"),
    ("import_draft_items", "validation_status"),
    ("import_drafts", "status"),
    ("weekly_batches", "status"),
}

STRICT_DATABASE_SCOPE_COLUMNS = {
    ("entitlement_grant_batches", "theater_id"),
    ("entitlement_item_types", "theater_id"),
    ("entitlement_items", "theater_id"),
    ("entitlement_ledger_entries", "theater_id"),
}


def include_schema_object(
    object_: object,
    name: str | None,
    type_: str,
    _reflected: bool,
    _compare_to: object,
) -> bool:
    if type_ == "column" and (object_.table.name, name) in STRICT_DATABASE_SCOPE_COLUMNS:
        return False
    return True


def compare_schema_type(
    _context: object,
    inspected_column: object,
    metadata_column: object,
    inspected_type: object,
    metadata_type: object,
) -> bool | None:
    key = (metadata_column.table.name, metadata_column.name)
    if (
        key in STRING_BACKED_ENUM_COLUMNS
        and isinstance(inspected_type, sa.String)
        and isinstance(metadata_type, sa.Enum)
    ):
        return False
    return None


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=compare_schema_type,
        include_object=include_schema_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=compare_schema_type,
            include_object=include_schema_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
