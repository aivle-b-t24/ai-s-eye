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

    def fake_create(request):
        captured["request"] = request
        return FirebaseUserSummary(
            uid="owner-002",
            email=request.email,
            name=request.name,
            role="store_manager",
            store_id=request.store_id,
        )

    app.dependency_overrides[get_current_user] = lambda: admin_user
    monkeypatch.setattr(main_module, "create_store_manager_account", fake_create)
    try:
        response = client.post(
            "/api/admin/users",
            json={
                "email": "Owner02@AICafe.com ",
                "name": " 수완점 점주 ",
                "store_id": "store-002",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json() == {
        "uid": "owner-002",
        "email": "owner02@aicafe.com",
        "name": "수완점 점주",
        "role": "store_manager",
        "store_id": "store-002",
        "disabled": False,
    }
    assert captured["request"].store_id == "store-002"


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
                "store_id": "store-002",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"] == "본사 관리자 권한이 필요합니다"


def test_admin_user_creation_rejects_unknown_store(
    client: TestClient,
    admin_user: CurrentUser,
) -> None:
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        response = client.post(
            "/api/admin/users",
            json={
                "email": "owner99@aicafe.com",
                "name": "미등록 매장 점주",
                "store_id": "store-999",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["detail"] == "지원하지 않는 매장입니다"
