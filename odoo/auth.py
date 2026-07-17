"""Authentication utilities and FastAPI dependency.

Loads JWT secret and cookie settings from environment at import time.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt

SECRET_KEY = os.environ.get("SECRET_KEY")
ALGORITHM = "HS256"
TOKEN_TTL_HOURS = int(os.environ.get("AUTH_TOKEN_TTL_HOURS", "24"))
COOKIE_SECURE = os.environ.get("AUTH_COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.environ.get("AUTH_COOKIE_SAMESITE", "lax")

if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY environment variable is required for JWT auth. "
        "Set it before starting the application."
    )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def get_password_hash(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_access_token(user_id: str, email: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=TOKEN_TTL_HOURS)
    to_encode = {
        "sub": user_id,
        "email": email,
        "role": role,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


def get_current_user(request: Request) -> dict:
    """FastAPI dependency: verify JWT cookie and return the user row.

    Raises HTTPException(401) if the token is missing, invalid, or expired,
    or if the user no longer exists/is inactive.
    """
    from config_store import get_store

    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    try:
        payload = decode_access_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    email = payload.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
        )
    user = get_store().get_user_by_email(email)
    if user is None or not user.get("active"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


def get_current_user_optional(request: Request) -> dict | None:
    """Optional variant for routes that behave differently when logged in."""
    try:
        return get_current_user(request)
    except HTTPException:
        return None


def get_user_permissions(user_id: str) -> set[str]:
    """Return the set of permission ids assigned to a user."""
    from config_store import get_store

    return get_store().get_user_permissions(user_id)


def require_permission(permission_id: str):
    """FastAPI dependency factory: verify the current user has a permission."""

    def _check_permission(user: dict = Depends(get_current_user)):
        from config_store import get_store

        permissions = get_store().get_user_permissions(user["id"])
        if permission_id not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied",
            )
        return user

    return _check_permission
