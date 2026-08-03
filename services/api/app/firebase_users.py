"""Firebase Authentication 사용자 계정을 본사 관리자 대신 관리한다."""

from __future__ import annotations

import secrets

from firebase_admin import auth as firebase_auth

from .auth import STORE_MANAGER_ROLE, get_firebase_app
from .models import FirebaseUserSummary, StoreManagerAccountCreate


class FirebaseUserAlreadyExistsError(Exception):
    """같은 이메일의 Firebase 사용자가 이미 존재한다."""


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
        # 사용자가 로그인 화면의 비밀번호 설정 메일로 직접 비밀번호를 정한다.
        password=secrets.token_urlsafe(32),
        email_verified=False,
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


def list_managed_accounts() -> list[FirebaseUserSummary]:
    users = firebase_auth.list_users(app=get_firebase_app()).iterate_all()
    summaries = [_summary(user) for user in users]
    return sorted(summaries, key=lambda user: (user.role or "", user.email))
