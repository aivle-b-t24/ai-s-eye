"""Firebase Authentication 사용자 계정을 본사 관리자 대신 관리한다."""

from __future__ import annotations

from firebase_admin import auth as firebase_auth

from .auth import STORE_MANAGER_ROLE, get_firebase_app
from .models import (
    FirebaseUserSummary,
    StoreManagerAccountCreate,
    StoreManagerPasswordUpdate,
)


class FirebaseUserAlreadyExistsError(Exception):
    """같은 이메일의 Firebase 사용자가 이미 존재한다."""


class FirebaseUserNotFoundError(Exception):
    """삭제하려는 Firebase 사용자가 존재하지 않는다."""


class FirebaseUserNotStoreManagerError(Exception):
    """점주가 아닌 계정에 삭제를 요청했다."""


def _summary(user: firebase_auth.UserRecord) -> FirebaseUserSummary:
    claims = user.custom_claims or {}
    return FirebaseUserSummary(
        uid=user.uid,
        email=user.email or "",
        name=user.display_name or user.email or "사용자",
        role=claims.get("role"),
        store_id=claims.get("store_id"),
        disabled=user.disabled,
    )


def create_store_manager_account(
    request: StoreManagerAccountCreate,
) -> FirebaseUserSummary:
    app = get_firebase_app()
    try:
        firebase_auth.get_user_by_email(request.email, app=app)
    except firebase_auth.UserNotFoundError:
        pass
    else:
        raise FirebaseUserAlreadyExistsError(request.email)

    user = firebase_auth.create_user(
        email=request.email,
        display_name=request.name,
        password=request.password,
        # 가상 이메일 계정도 본사가 발급할 수 있으므로 메일 확인을 요구하지 않는다.
        email_verified=True,
        app=app,
    )
    try:
        firebase_auth.set_custom_user_claims(
            user.uid,
            {
                "role": STORE_MANAGER_ROLE,
                "store_id": request.store_id,
            },
            app=app,
        )
        user = firebase_auth.get_user(user.uid, app=app)
    except Exception:
        # 권한 설정까지 끝나지 않은 반쪽 계정은 남기지 않는다.
        firebase_auth.delete_user(user.uid, app=app)
        raise
    return _summary(user)


def delete_store_manager_account(uid: str) -> None:
    app = get_firebase_app()
    try:
        user = firebase_auth.get_user(uid, app=app)
    except firebase_auth.UserNotFoundError as exc:
        raise FirebaseUserNotFoundError(uid) from exc

    claims = user.custom_claims or {}
    if claims.get("role") != STORE_MANAGER_ROLE:
        raise FirebaseUserNotStoreManagerError(uid)

    firebase_auth.delete_user(uid, app=app)


def update_store_manager_password(
    uid: str,
    request: StoreManagerPasswordUpdate,
) -> None:
    app = get_firebase_app()
    try:
        user = firebase_auth.get_user(uid, app=app)
    except firebase_auth.UserNotFoundError as exc:
        raise FirebaseUserNotFoundError(uid) from exc

    claims = user.custom_claims or {}
    if claims.get("role") != STORE_MANAGER_ROLE:
        raise FirebaseUserNotStoreManagerError(uid)

    firebase_auth.update_user(uid, password=request.password, app=app)
    firebase_auth.revoke_refresh_tokens(uid, app=app)


def list_managed_accounts() -> list[FirebaseUserSummary]:
    users = firebase_auth.list_users(app=get_firebase_app()).iterate_all()
    summaries = [_summary(user) for user in users]
    return sorted(summaries, key=lambda user: (user.role or "", user.email))
