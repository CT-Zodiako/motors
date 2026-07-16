"""Shared fixtures for the odoo backend test suite.

- Adds the backend root (odoo/) to sys.path so `from main import app` works.
- `client`: FastAPI TestClient without lifespan (avoids starting the scheduler).
- `store`: fresh InMemoryConfigStore per test, injected via set_store(...).
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    # Plain TestClient (no context manager): startup/shutdown events (scheduler) do NOT fire.
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def store():
    """Fresh InMemoryConfigStore per test, seeded with defaults, injected via set_store(...)."""
    from config_store.memory_store import InMemoryConfigStore
    from config_store.bootstrap import seed_defaults
    from config_store import set_store

    _store = InMemoryConfigStore()
    seed_defaults(_store)
    set_store(_store)
    yield _store

