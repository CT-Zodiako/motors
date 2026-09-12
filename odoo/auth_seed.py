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
SUPPORT_USER_EMAIL = "support@gmail.com"


def seed_support_user(store: Any, get_password_hash: Callable[[str], str]) -> None:
    """Ensure the separate support account is active/admin with seeded permissions.

    New accounts use DEFAULT_USER_PASSWORD (the legacy demo convention: 123456).
    Existing passwords are never reset. Change the demo password before deployment.
    This explicit bootstrap account is restored to admin on each startup.
    """
    from config_store.bootstrap import _SEED_PERMISSIONS

    store.seed_permission_defaults()
    user = store.get_user_by_email(SUPPORT_USER_EMAIL)
    if user is None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        user = store.create_user({
            "id": str(uuid.uuid4()), "email": SUPPORT_USER_EMAIL,
            "password_hash": get_password_hash(DEFAULT_USER_PASSWORD),
            "role": "admin", "active": True, "created_at": now, "updated_at": now,
        })
    elif user.get("role") != "admin" or not user.get("active"):
        user = store.update_user(user["id"], {"role": "admin", "active": True})
    held = store.get_user_permissions(user["id"])
    for permission in _SEED_PERMISSIONS:
        if permission["id"] not in held:
            store.assign_user_permission(user["id"], permission["id"])


def grant_seeded_permissions_to_existing_user(store: Any, email: str) -> None:
    """Grant seeded permissions without creating or updating the account."""
    from config_store.bootstrap import _SEED_PERMISSIONS

    user = store.get_user_by_email(email)
    if user is None:
        return
    held = store.get_user_permissions(user["id"])
    for permission in _SEED_PERMISSIONS:
        if permission["id"] not in held:
            store.assign_user_permission(user["id"], permission["id"])


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
