from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from auth import get_password_hash, require_permission
from config_store import get_store, ConflictError, NotFoundError

router = APIRouter(prefix="/admin", tags=["admin"])


class UserCreateIn(BaseModel):
    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    role: str = Field(default="user")
    active: bool = Field(default=True)


class UserUpdateIn(BaseModel):
    role: str | None = Field(None)
    active: bool | None = Field(None)


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    active: bool


class PermissionAssignmentIn(BaseModel):
    permission_id: str = Field(..., min_length=1)
    granted: bool = Field(...)


@router.get("/users", response_model=list[UserOut])
def list_users(user: dict = Depends(require_permission("menu.admin.usuarios"))):
    rows = get_store().list_users()
    return [{"id": r["id"], "email": r["email"], "role": r["role"], "active": r["active"]} for r in rows]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreateIn, user: dict = Depends(require_permission("menu.admin.usuarios"))):
    try:
        created = get_store().create_user({
            "id": str(uuid.uuid4()),
            "email": body.email.lower(),
            "password_hash": get_password_hash(body.password),
            "role": body.role,
            "active": body.active,
            "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
            "updated_at": datetime.now(timezone.utc).replace(tzinfo=None),
        })
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"id": created["id"], "email": created["email"], "role": created["role"], "active": created["active"]}


@router.get("/users/{user_id}")
def get_user(user_id: str, user: dict = Depends(require_permission("menu.admin.usuarios"))):
    row = get_store().get_user_by_id(user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    permissions = sorted(get_store().get_user_permissions(user_id))
    return {
        "id": row["id"],
        "email": row["email"],
        "role": row["role"],
        "active": row["active"],
        "permissions": permissions,
    }


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: str, body: UserUpdateIn, user: dict = Depends(require_permission("menu.admin.usuarios"))):
    patch: dict[str, Any] = {}
    if body.role is not None:
        patch["role"] = body.role
    if body.active is not None:
        patch["active"] = body.active
    try:
        updated = get_store().update_user(user_id, patch)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": updated["id"], "email": updated["email"], "role": updated["role"], "active": updated["active"]}


@router.delete("/users/{user_id}")
def delete_user(user_id: str, user: dict = Depends(require_permission("menu.admin.usuarios"))):
    if get_store().get_user_by_id(user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    get_store().delete_user(user_id)
    return {"deleted": user_id}


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: str, body: dict, user: dict = Depends(require_permission("menu.admin.usuarios"))):
    new_password = body.get("password")
    if not new_password or not isinstance(new_password, str) or len(new_password) < 1:
        raise HTTPException(status_code=400, detail="password must be a non-empty string")
    try:
        get_store().update_user_password(user_id, get_password_hash(new_password))
    except NotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}


@router.post("/users/{user_id}/permissions")
def set_permission(user_id: str, body: PermissionAssignmentIn, user: dict = Depends(require_permission("menu.admin.usuarios"))):
    if get_store().get_user_by_id(user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    if body.granted:
        try:
            get_store().assign_user_permission(user_id, body.permission_id)
        except NotFoundError:
            raise HTTPException(status_code=404, detail="Permission not found")
    else:
        get_store().revoke_user_permission(user_id, body.permission_id)
    return {"ok": True}


@router.get("/permissions")
def list_permissions(user: dict = Depends(require_permission("menu.admin.usuarios"))):
    return {"permissions": get_store().list_permissions()}

