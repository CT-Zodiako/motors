from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from auth import (
    COOKIE_SAMESITE,
    COOKIE_SECURE,
    TOKEN_TTL_HOURS,
    create_access_token,
    get_current_user,
    get_password_hash,
    get_user_permissions,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=1)


class UserOut(BaseModel):
    id: str
    email: str
    role: str


@router.post("/login")
def login(body: LoginIn, response: Response) -> dict:
    from config_store import get_store

    user = get_store().get_user_by_email(body.email)
    if user is None or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    token = create_access_token(user["id"], user["email"], user["role"])
    max_age = TOKEN_TTL_HOURS * 3600
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
        max_age=max_age,
    )
    return {"user": UserOut(id=user["id"], email=user["email"], role=user["role"])}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(
        key="access_token",
        path="/",
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
    )
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: dict = Depends(get_current_user)) -> dict:
    return {k: user[k] for k in ("id", "email", "role")}


@router.get("/permissions")
def permissions(user: dict = Depends(get_current_user)) -> dict:
    return {"permissions": sorted(get_user_permissions(user["id"]))}


@router.post("/change-password")
def change_password(
    body: ChangePasswordIn, user: dict = Depends(get_current_user)
) -> dict:
    if body.current_password == body.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from current password",
        )
    if not verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )
    from config_store import get_store

    get_store().update_user_password(user["id"], get_password_hash(body.new_password))
    return {"ok": True}
