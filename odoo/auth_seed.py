"""Default user seeding helper.

Keeps the startup seed logic separate from auth.py so that auth.py can be
imported without triggering a config_store import at module load time.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable


DEFAULT_USER_EMAIL = "soporte@gmail.com"
DEFAULT_USER_PASSWORD = "123456"
DEFAULT_USER_ROLE = "admin"


def seed_default_user(
    store: Any,
    get_password_hash: Callable[[str], str],
    email: str = DEFAULT_USER_EMAIL,
    password: str = DEFAULT_USER_PASSWORD,
    role: str = DEFAULT_USER_ROLE,
) -> None:
    """Create the default admin user if the users table is empty."""
    if store.count_users() > 0:
        return
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    user = store.create_user({
        "id": str(uuid.uuid4()),
        "email": email.lower(),
        "password_hash": get_password_hash(password),
        "role": role,
        "active": True,
        "created_at": now,
        "updated_at": now,
    })
    # Grant the seeded admin user all menu permissions so the app remains usable.
    store.seed_permission_defaults()
    for perm in store.list_permissions():
        store.assign_user_permission(user["id"], perm["id"])
