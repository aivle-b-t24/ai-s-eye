"""Firebase Authentication 사용자 계정을 본사 관리자 대신 관리한다."""

from __future__ import annotations

from datetime import datetime, timezone

from firebase_admin import auth as firebase_auth

from .auth import ADMIN_ROLE, STORE_MANAGER_ROLE, get_firebase_app
from .models import FirebaseUserSummary, StoreManagerPasswordUpdate

HEAD_OFFICE_STORE_ID = "head-office"


def _now_iso() -> str:
    """비밀번호 유효기간 계산용 변경 시각(UTC ISO 8601)."""
    return datetime.now(timezone.utc).isoformat()


class FirebaseUserAlreadyExistsError(Exception):
    """같은 이메일의 Firebase 사용자가 이미 존재한다."""


class FirebaseUserNotFoundError(Exception):
    """삭제하려는 Firebase 사용자가 존재하지 않는다."""


class FirebaseUserNotStoreManagerError(Exception):
    """점주가 아닌 계정에 삭제를 요청했다."""


def _summary(
    user: firebase_auth.UserRecord,
    *,
    store_name: str | None = None,
) -> FirebaseUserSummary:
    claims = user.custom_claims or {}
    return FirebaseUserSummary(
        uid=user.uid,
        email=user.email or "",
        name=user.display_name or user.email or "사용자",
        role=claims.get("role"),
        store_id=claims.get("store_id"),
        store_name=store_name,
        disabled=user.disabled,
        password_changed_at=claims.get("password_changed_at"),
    )


def create_store_manager_account(
    *,
    email: str,
    name: str,
    password: str,
    store_id: str,
    store_name: str | None = None,
) -> FirebaseUserSummary:
    app = get_firebase_app()
    try:
        firebase_auth.get_user_by_email(email, app=app)
    except firebase_auth.UserNotFoundError:
        pass
    else:
        raise FirebaseUserAlreadyExistsError(email)

    user = firebase_auth.create_user(
        email=email,
        display_name=name,
        password=password,
        # 가상 이메일 계정도 본사가 발급할 수 있으므로 메일 확인을 요구하지 않는다.
        email_verified=True,
        app=app,
    )
    try:
        firebase_auth.set_custom_user_claims(
            user.uid,
            {
                "role": STORE_MANAGER_ROLE,
                "store_id": store_id,
                "password_changed_at": _now_iso(),
            },
            app=app,
        )
        user = firebase_auth.get_user(user.uid, app=app)
    except Exception:
        # 권한 설정까지 끝나지 않은 반쪽 계정은 남기지 않는다.
        firebase_auth.delete_user(user.uid, app=app)
        raise
    return _summary(user, store_name=store_name)


def create_hq_admin_account(
    *,
    email: str,
    name: str,
    password: str,
    company: str,
) -> FirebaseUserSummary:
    """본사 관리자(admin) 계정을 셀프 회원가입으로 생성한다."""
    app = get_firebase_app()
    try:
        firebase_auth.get_user_by_email(email, app=app)
    except firebase_auth.UserNotFoundError:
        pass
    else:
        raise FirebaseUserAlreadyExistsError(email)

    user = firebase_auth.create_user(
        email=email,
        display_name=name,
        # 비밀번호는 Firebase가 일방향 해시로 저장하며 평문은 보관하지 않는다.
        password=password,
        email_verified=True,
        app=app,
    )
    try:
        firebase_auth.set_custom_user_claims(
            user.uid,
            {
                "role": ADMIN_ROLE,
                "store_id": HEAD_OFFICE_STORE_ID,
                "company": company,
                "password_changed_at": _now_iso(),
            },
            app=app,
        )
        user = firebase_auth.get_user(user.uid, app=app)
    except Exception:
        # 권한 설정까지 끝나지 않은 반쪽 계정은 남기지 않는다.
        firebase_auth.delete_user(user.uid, app=app)
        raise
    return _summary(user)


def delete_store_manager_account(uid: str) -> str | None:
    app = get_firebase_app()
    try:
        user = firebase_auth.get_user(uid, app=app)
    except firebase_auth.UserNotFoundError as exc:
        raise FirebaseUserNotFoundError(uid) from exc

    claims = user.custom_claims or {}
    if claims.get("role") != STORE_MANAGER_ROLE:
        raise FirebaseUserNotStoreManagerError(uid)

    store_id = claims.get("store_id")
    firebase_auth.delete_user(uid, app=app)
    return store_id


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
    # 비밀번호를 바꾸면 유효기간을 초기화한다(만료 표시 해제).
    firebase_auth.set_custom_user_claims(
        uid,
        {**claims, "password_changed_at": _now_iso()},
        app=app,
    )
    firebase_auth.revoke_refresh_tokens(uid, app=app)


def list_managed_accounts() -> list[FirebaseUserSummary]:
    users = firebase_auth.list_users(app=get_firebase_app()).iterate_all()
    summaries = [_summary(user) for user in users]
    return sorted(summaries, key=lambda user: (user.role or "", user.email))
