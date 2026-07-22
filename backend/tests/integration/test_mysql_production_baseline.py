import os
import subprocess

import pytest
from sqlalchemy import create_engine, text


TEST_URL = os.getenv("TEST_MYSQL_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="TEST_MYSQL_DATABASE_URL is not configured")


def _assert_isolated_test_database() -> None:
    database = TEST_URL.rsplit("/", 1)[-1].split("?", 1)[0]
    if "test" not in database.lower():
        raise RuntimeError("TEST_MYSQL_DATABASE_URL must name an isolated test database")


def test_mysql_clean_migration_reaches_head():
    _assert_isolated_test_database()
    engine = create_engine(TEST_URL)
    with engine.begin() as connection:
        connection.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for table in connection.execute(text("SHOW TABLES")).scalars().all():
            connection.execute(text(f"DROP TABLE `{table}`"))
        connection.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    environment = {**os.environ, "DATABASE_URL": TEST_URL}
    subprocess.run([".venv/bin/alembic", "upgrade", "head"], check=True, env=environment)
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "0023_query_hardening"
        )
