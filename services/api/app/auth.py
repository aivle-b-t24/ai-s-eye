from dataclasses import dataclass
from functools import lru_cache
import secrets

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
    email: str
    name: str
    role: str
    store_id: str

    def response(self) -> dict[str, str]:
        return {
            "uid": self.uid,
            "id": self.email.split("@", 1)[0],
            "email": self.email,
            "name": self.name,
            "role": self.role,
            "storeId": self.store_id,
        }


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
        name="ai-s-eye-api",
    )


def _internal_service_user() -> CurrentUser:
    return CurrentUser(
        uid="internal-service",
        email="internal@aicafe.local",
        name="내부 서비스",
        role=ADMIN_ROLE,
        store_id="head-office",
    )


def _valid_internal_key(value: str | None) -> bool:
    expected = get_settings().internal_api_key
    return bool(expected and value and secrets.compare_digest(value, expected))


def get_current_user(
    authorization: str | None = Header(default=None),
    x_internal_api_key: str | None = Header(default=None),
) -> CurrentUser:
    settings = get_settings()
    if _valid_internal_key(x_internal_api_key):
        return _internal_service_user()
    if not settings.auth_required:
        return _internal_service_user()
    if not settings.firebase_project_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firebase project is not configured",
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise _unauthorized()

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise _unauthorized()

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

    email = str(claims.get("email") or "")
    return CurrentUser(
        uid=str(claims["uid"]),
        email=email,
        name=str(claims.get("name") or email.split("@", 1)[0] or "사용자"),
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


def require_store_access(
    store_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    if user.role == ADMIN_ROLE or user.store_id == store_id:
        return user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="담당 매장에만 접근할 수 있습니다",
    )


def require_internal_service(
    x_internal_api_key: str | None = Header(default=None),
) -> None:
    settings = get_settings()
    if not settings.auth_required:
        return
    if not _valid_internal_key(x_internal_api_key):
        raise _unauthorized("유효한 내부 서비스 키가 필요합니다")
