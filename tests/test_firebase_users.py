from types import SimpleNamespace

import pytest

import app.firebase_users as firebase_users


def test_delete_store_manager_account_deletes_store_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deleted = []
    firebase_app = object()
    user = SimpleNamespace(custom_claims={"role": "store_manager"})

    monkeypatch.setattr(firebase_users, "get_firebase_app", lambda: firebase_app)
    monkeypatch.setattr(
        firebase_users.firebase_auth,
        "get_user",
        lambda uid, app: user,
    )
    monkeypatch.setattr(
        firebase_users.firebase_auth,
        "delete_user",
        lambda uid, app: deleted.append((uid, app)),
    )

    firebase_users.delete_store_manager_account("owner-002")

    assert deleted == [("owner-002", firebase_app)]


def test_delete_store_manager_account_rejects_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    firebase_app = object()
    user = SimpleNamespace(custom_claims={"role": "admin"})

    monkeypatch.setattr(firebase_users, "get_firebase_app", lambda: firebase_app)
    monkeypatch.setattr(
        firebase_users.firebase_auth,
        "get_user",
        lambda uid, app: user,
    )

    with pytest.raises(firebase_users.FirebaseUserNotStoreManagerError):
        firebase_users.delete_store_manager_account("admin-001")


def test_update_store_manager_password_updates_and_revokes_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    firebase_app = object()
    user = SimpleNamespace(custom_claims={"role": "store_manager"})
    updated = []
    revoked = []
    request = SimpleNamespace(password="new-temporary-password-2026")

    monkeypatch.setattr(firebase_users, "get_firebase_app", lambda: firebase_app)
    monkeypatch.setattr(
        firebase_users.firebase_auth,
        "get_user",
        lambda uid, app: user,
    )
    monkeypatch.setattr(
        firebase_users.firebase_auth,
        "update_user",
        lambda uid, password, app: updated.append((uid, password, app)),
    )
    monkeypatch.setattr(
        firebase_users.firebase_auth,
        "revoke_refresh_tokens",
        lambda uid, app: revoked.append((uid, app)),
    )
    monkeypatch.setattr(
        firebase_users.firebase_auth,
        "set_custom_user_claims",
        lambda uid, claims, app: None,
    )

    firebase_users.update_store_manager_password("owner-002", request)

    assert updated == [("owner-002", "new-temporary-password-2026", firebase_app)]
    assert revoked == [("owner-002", firebase_app)]


def test_update_store_manager_password_rejects_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    firebase_app = object()
    user = SimpleNamespace(custom_claims={"role": "admin"})
    request = SimpleNamespace(password="new-temporary-password-2026")

    monkeypatch.setattr(firebase_users, "get_firebase_app", lambda: firebase_app)
    monkeypatch.setattr(
        firebase_users.firebase_auth,
        "get_user",
        lambda uid, app: user,
    )

    with pytest.raises(firebase_users.FirebaseUserNotStoreManagerError):
        firebase_users.update_store_manager_password("admin-001", request)
