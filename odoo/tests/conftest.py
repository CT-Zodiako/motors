"""Shared fixtures for the odoo backend test suite.

- Adds the backend root (odoo/) to sys.path so `import db`, `from main import app` work.
- `client`: FastAPI TestClient without lifespan (avoids starting the scheduler).
- `cleanup`: autouse fixture that removes any row created by tests (names prefixed `t_`).
  Test data NEVER touches seed rows.
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import execute as pg_execute  # noqa: E402
from main import app  # noqa: E402

TEST_PREFIX = "t_"


@pytest.fixture(scope="session", autouse=True)
def migrated_db():
    """Guarantee the schema (incl. query-categories migration) exists before any API test."""
    import init_db

    init_db.init()
    yield


@pytest.fixture(scope="session")
def client(migrated_db):
    # Plain TestClient (no context manager): startup/shutdown events (scheduler) do NOT fire.
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def cleanup():
    yield
    # FK order: queries reference categories, so delete queries first.
    pg_execute("DELETE FROM odoo_queries WHERE name LIKE 't\\_%' ESCAPE '\\'")
    pg_execute(
        "DELETE FROM query_categories WHERE name LIKE 't\\_%' ESCAPE '\\'"
        # table may not exist yet in early RED runs; guard below
    ) if _table_exists("query_categories") else None


def _table_exists(table: str) -> bool:
    from db import query as pg_query

    rows = pg_query(
        "SELECT 1 AS ok FROM information_schema.tables WHERE table_name = %s", (table,)
    )
    return bool(rows)
