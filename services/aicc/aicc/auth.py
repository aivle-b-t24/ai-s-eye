from dataclasses import dataclass
from functools import lru_cache

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials
from fastapi import Depends, Header, HTTPException, status

from .config import get_settings


STORE_MANAGER_ROLE = "store_manager"
ADMIN_ROLE = "admin"


@dataclass(frozen=True)
class CurrentUser:
    uid: str
    role: str
    store_id: str


def _unauthorized(detail: str = "로그인이 필요합니다") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


@lru_cache
def get_firebase_app() -> firebase_admin.App:
    settings = get_settings()
    options = {"projectId": settings.firebase_project_id}
    credential = (
        credentials.Certificate(str(settings.firebase_credentials_path))
        if settings.firebase_credentials_path
        else None
    )
    return firebase_admin.initialize_app(
        credential=credential,
        options=options,
        name="ai-s-eye-aicc",
    )


def get_current_user(
    authorization: str | None = Header(default=None),
) -> CurrentUser:
    settings = get_settings()
    if not settings.auth_required:
        return CurrentUser(uid="development", role=ADMIN_ROLE, store_id="head-office")
    if not authorization or not authorization.startswith("Bearer "):
        raise _unauthorized()

    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = firebase_auth.verify_id_token(token, app=get_firebase_app())
    except (
        ValueError,
        firebase_auth.InvalidIdTokenError,
        firebase_auth.ExpiredIdTokenError,
        firebase_auth.RevokedIdTokenError,
        firebase_auth.UserDisabledError,
    ) as exc:
        raise _unauthorized("유효하지 않거나 만료된 로그인입니다") from exc

    role = claims.get("role")
    store_id = claims.get("store_id")
    if role not in {STORE_MANAGER_ROLE, ADMIN_ROLE}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="계정에 서비스 역할이 지정되지 않았습니다",
        )
    if role == STORE_MANAGER_ROLE and not store_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="점주 계정에 담당 매장이 지정되지 않았습니다",
        )
    return CurrentUser(
        uid=str(claims["uid"]),
        role=str(role),
        store_id=str(store_id or "head-office"),
    )


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role != ADMIN_ROLE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="본사 관리자 권한이 필요합니다",
        )
    return user
