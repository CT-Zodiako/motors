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
    from auth import get_current_user

    _store = InMemoryConfigStore()
    seed_defaults(_store)
    # Seed the default support user so auth tests have a known account.
    from auth_seed import seed_default_user
    from auth import get_password_hash
    seed_default_user(_store, get_password_hash)
    # Provide a default authenticated user so existing router tests keep passing.
    _default_user = _store.create_user({
        "id": "test-user-id",
        "email": "test@example.com",
        "password_hash": "$2b$12$testhash",
        "role": "admin",
        "active": True,
        "created_at": None,
        "updated_at": None,
    })
    _store.seed_permission_defaults()
    for perm in _store.list_permissions():
        _store.assign_user_permission(_default_user["id"], perm["id"])
    set_store(_store)
    app.dependency_overrides[get_current_user] = lambda: _default_user
    yield _store
    app.dependency_overrides.pop(get_current_user, None)
