from fastapi.testclient import TestClient
import pytest

from app.auth import CurrentUser, get_current_user
from app.main import app
from app.models import FirebaseUserSummary
import app.main as main_module


@pytest.fixture
def owner_user() -> CurrentUser:
    return CurrentUser(
        uid="owner-001",
        email="owner01@aicafe.com",
        name="동명점 점주",
        role="store_manager",
        store_id="store-001",
    )


@pytest.fixture
def admin_user() -> CurrentUser:
    return CurrentUser(
        uid="admin-001",
        email="admin01@aicafe.com",
        name="본사 관리자",
        role="admin",
        store_id="head-office",
    )


def test_auth_me_returns_frontend_profile(
    client: TestClient,
    owner_user: CurrentUser,
) -> None:
    app.dependency_overrides[get_current_user] = lambda: owner_user
    try:
        response = client.get("/api/auth/me")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "uid": "owner-001",
        "id": "owner01",
        "email": "owner01@aicafe.com",
        "name": "동명점 점주",
        "role": "store_manager",
        "storeId": "store-001",
        "storeName": "동명점",
    }


def test_store_manager_can_only_access_assigned_store(
    client: TestClient,
    owner_user: CurrentUser,
) -> None:
    app.dependency_overrides[get_current_user] = lambda: owner_user
    try:
        own_store = client.get("/api/stores/store-001/menus")
        another_store = client.get("/api/stores/store-002/menus")
    finally:
        app.dependency_overrides.clear()

    assert own_store.status_code == 200
    assert another_store.status_code == 403
    assert another_store.json()["detail"] == "담당 매장에만 접근할 수 있습니다"


def test_store_manager_cannot_access_head_office_summary(
    client: TestClient,
    owner_user: CurrentUser,
) -> None:
    app.dependency_overrides[get_current_user] = lambda: owner_user
    try:
        response = client.get("/api/stores/summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"] == "본사 관리자 권한이 필요합니다"


def test_admin_can_create_store_manager_account(
    client: TestClient,
    admin_user: CurrentUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    def fake_create(**kwargs):
        captured["kwargs"] = kwargs
        return FirebaseUserSummary(
            uid="owner-002",
            email=kwargs["email"],
            name=kwargs["name"],
            role="store_manager",
            store_id=kwargs["store_id"],
            store_name=kwargs["store_name"],
        )

    app.dependency_overrides[get_current_user] = lambda: admin_user
    monkeypatch.setattr(main_module, "create_store_manager_account", fake_create)
    try:
        response = client.post(
            "/api/admin/users",
            json={
                "email": "Owner02@AICafe.com ",
                "name": " 상무점 점주 ",
                "store_name": " 상무점 ",
                "password": "temporary-password-2026",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["uid"] == "owner-002"
    assert body["email"] == "owner02@aicafe.com"
    assert body["name"] == "상무점 점주"
    assert body["role"] == "store_manager"
    assert body["store_id"].startswith("store-")
    assert body["store_name"] == "상무점"
    assert body["disabled"] is False
    assert captured["kwargs"]["store_id"] == body["store_id"]
    assert captured["kwargs"]["store_name"] == "상무점"
    assert captured["kwargs"]["password"] == "temporary-password-2026"


def test_admin_user_creation_rejects_duplicate_store_name(
    client: TestClient,
    admin_user: CurrentUser,
) -> None:
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        response = client.post(
            "/api/admin/users",
            json={
                "email": "owner99@aicafe.com",
                "name": "중복 매장 점주",
                "store_name": "동명점",
                "password": "temporary-password-2026",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["detail"] == "이미 등록된 매장명입니다"


def test_store_manager_cannot_create_accounts(
    client: TestClient,
    owner_user: CurrentUser,
) -> None:
    app.dependency_overrides[get_current_user] = lambda: owner_user
    try:
        response = client.post(
            "/api/admin/users",
            json={
                "email": "owner02@aicafe.com",
                "name": "수완점 점주",
                "store_name": "신규점",
                "password": "temporary-password-2026",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"] == "본사 관리자 권한이 필요합니다"


def test_admin_can_list_stores(
    client: TestClient,
    admin_user: CurrentUser,
) -> None:
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        response = client.get("/api/admin/stores")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    stores = {store["id"]: store["name"] for store in response.json()}
    assert stores["store-001"] == "동명점"
    assert stores["store-002"] == "수완점"


def test_admin_can_delete_store_manager_account(
    client: TestClient,
    admin_user: CurrentUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deleted = []

    app.dependency_overrides[get_current_user] = lambda: admin_user
    monkeypatch.setattr(
        main_module,
        "delete_store_manager_account",
        lambda uid: deleted.append(uid),
    )
    try:
        response = client.delete("/api/admin/users/owner-002")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert response.content == b""
    assert deleted == ["owner-002"]


def test_store_manager_cannot_delete_accounts(
    client: TestClient,
    owner_user: CurrentUser,
) -> None:
    app.dependency_overrides[get_current_user] = lambda: owner_user
    try:
        response = client.delete("/api/admin/users/owner-002")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"] == "본사 관리자 권한이 필요합니다"


def test_admin_can_update_store_manager_password(
    client: TestClient,
    admin_user: CurrentUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updated = []

    app.dependency_overrides[get_current_user] = lambda: admin_user
    monkeypatch.setattr(
        main_module,
        "update_store_manager_password",
        lambda uid, request: updated.append((uid, request.password)),
    )
    try:
        response = client.patch(
            "/api/admin/users/owner-002/password",
            json={"password": "new-temporary-password-2026"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert response.content == b""
    assert updated == [("owner-002", "new-temporary-password-2026")]


def test_store_manager_cannot_update_passwords(
    client: TestClient,
    owner_user: CurrentUser,
) -> None:
    app.dependency_overrides[get_current_user] = lambda: owner_user
    try:
        response = client.patch(
            "/api/admin/users/owner-002/password",
            json={"password": "new-temporary-password-2026"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"] == "본사 관리자 권한이 필요합니다"
