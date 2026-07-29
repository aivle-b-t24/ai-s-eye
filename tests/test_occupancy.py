import pytest
from fastapi.testclient import TestClient

from app.main import occupancy_repository


@pytest.fixture(autouse=True)
def reset_occupancy_repository():
    occupancy_repository.clear()
    yield
    occupancy_repository.clear()


def valid_twin_frame(store_id: str = "store-001") -> dict:
    return {
        "schema_version": "1.0",
        "store_id": store_id,
        "camera_id": f"{store_id}-cam1",
        "mode": "live",
        "captured_at": "2026-07-28T10:00:00+09:00",
        "coordinate_space": "normalized_image",
        "agents": [
            {
                "id": "customer-17",
                "x": 0.45,
                "y": 0.32,
                "role": "customer",
                "state": "queue",
                "zone": "waiting",
            },
            {
                "id": "staff-3",
                "x": 0.72,
                "y": 0.48,
                "role": "staff",
                "state": "working",
                "zone": "staff",
            },
        ],
    }


def test_store_occupancy_can_be_saved_and_read(client: TestClient) -> None:
    payload = valid_twin_frame()

    save_response = client.post(
        "/internal/stores/store-001/occupancy",
        json=payload,
    )
    read_response = client.get("/api/stores/store-001/occupancy/latest")

    assert save_response.status_code == 201
    assert save_response.json()["saved"] is True
    assert read_response.status_code == 200
    assert read_response.json() == payload


def test_floor_coordinate_space_is_rejected(client: TestClient) -> None:
    payload = valid_twin_frame()
    payload["coordinate_space"] = "normalized_floor"

    response = client.post(
        "/internal/stores/store-001/occupancy",
        json=payload,
    )

    assert response.status_code == 422


def test_occupancy_is_kept_separately_by_store(client: TestClient) -> None:
    store_one = valid_twin_frame("store-001")
    store_two = valid_twin_frame("store-002")
    store_two["agents"][0]["x"] = 0.8

    client.post("/internal/stores/store-001/occupancy", json=store_one)
    client.post("/internal/stores/store-002/occupancy", json=store_two)

    first = client.get("/api/stores/store-001/occupancy/latest").json()
    second = client.get("/api/stores/store-002/occupancy/latest").json()

    assert first["store_id"] == "store-001"
    assert second["store_id"] == "store-002"
    assert first["agents"][0]["x"] == 0.45
    assert second["agents"][0]["x"] == 0.8


def test_missing_occupancy_returns_404(client: TestClient) -> None:
    response = client.get("/api/stores/store-001/occupancy/latest")

    assert response.status_code == 404
    assert response.json()["detail"] == "Occupancy not found"


def test_path_and_body_store_ids_must_match(client: TestClient) -> None:
    response = client.post(
        "/internal/stores/store-001/occupancy",
        json=valid_twin_frame("store-002"),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Path store_id and body store_id must match"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [("x", -0.01), ("x", 1.01), ("y", -0.01), ("y", 1.01)],
)
def test_occupancy_rejects_out_of_range_coordinates(
    client: TestClient,
    field: str,
    value: float,
) -> None:
    payload = valid_twin_frame()
    payload["agents"][0][field] = value

    response = client.post(
        "/internal/stores/store-001/occupancy",
        json=payload,
    )

    assert response.status_code == 422


def test_occupancy_requires_timezone(client: TestClient) -> None:
    payload = valid_twin_frame()
    payload["captured_at"] = "2026-07-28T10:00:00"

    response = client.post(
        "/internal/stores/store-001/occupancy",
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "captured_at must include a timezone"


def test_unknown_store_is_rejected(client: TestClient) -> None:
    payload = valid_twin_frame("store-unknown")

    response = client.post(
        "/internal/stores/store-unknown/occupancy",
        json=payload,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Store not found"
