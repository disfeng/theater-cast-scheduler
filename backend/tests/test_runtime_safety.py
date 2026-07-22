import pytest
from sqlalchemy import text

from app.services.readiness import check_database_readiness

from app.core.config import Settings


def production_settings(**overrides):
    values = {
        "app_env": "production",
        "database_url": "mysql+pymysql://app:strong-password@db/theater",
        "jwt_secret": "a-production-secret-that-is-long-and-random",
        "cors_allowed_origins": "https://scheduler.example.com",
        "allow_demo_admin": False,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"jwt_secret": "local-dev-secret-change-before-production"}, "JWT_SECRET"),
        ({"database_url": "mysql+pymysql://root:password@localhost/db"}, "DATABASE_URL"),
        ({"cors_allowed_origins": "*"}, "CORS_ALLOWED_ORIGINS"),
        ({"allow_demo_admin": True}, "ALLOW_DEMO_ADMIN"),
    ],
)
def test_production_rejects_unsafe_defaults(overrides, message):
    with pytest.raises(ValueError, match=message):
        production_settings(**overrides).validate_runtime_safety()


def test_production_accepts_explicit_safe_configuration():
    production_settings().validate_runtime_safety()


def test_cors_origins_are_trimmed_and_split():
    settings = Settings(cors_allowed_origins="http://localhost:7003, http://127.0.0.1:7003")
    assert settings.cors_origins == ["http://localhost:7003", "http://127.0.0.1:7003"]


def test_database_readiness_requires_current_migration(db_session):
    db_session.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
    db_session.execute(text("INSERT INTO alembic_version VALUES ('old_revision')"))
    with pytest.raises(RuntimeError, match="migration_not_current"):
        check_database_readiness(db_session, expected_heads={"current_revision"})


def test_database_readiness_accepts_current_migration(db_session):
    db_session.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
    db_session.execute(text("INSERT INTO alembic_version VALUES ('current_revision')"))
    assert check_database_readiness(db_session, expected_heads={"current_revision"}) == {
        "database": "ok",
        "migration": "ok",
    }
from pathlib import Path
import tomllib

def test_backend_package_discovery_only_includes_application_package():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())

    assert pyproject["tool"]["setuptools"]["packages"]["find"] == {
        "include": ["app*"]
    }
