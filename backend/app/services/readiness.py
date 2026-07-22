from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.orm import Session


def migration_heads() -> set[str]:
    backend_dir = Path(__file__).resolve().parents[2]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "migrations"))
    return set(ScriptDirectory.from_config(config).get_heads())


def check_database_readiness(
    session: Session, *, expected_heads: set[str] | None = None
) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    current = set(session.execute(text("SELECT version_num FROM alembic_version")).scalars())
    expected = expected_heads if expected_heads is not None else migration_heads()
    if current != expected:
        raise RuntimeError("migration_not_current")
    return {"database": "ok", "migration": "ok"}
