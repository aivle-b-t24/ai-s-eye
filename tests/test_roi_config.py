from fastapi.testclient import TestClient


def _payload(*, source: str = "manual", offset: int = 0) -> dict:
    return {
        "coordinate_space": "normalized_1000",
        "image_size": {"width": 1920, "height": 1080},
        "source": source,
        "zones": [
            {
                "id": "staff-1",
                "type": "staff",
                "label": "직원 구역",
                "polygon": [
                    {"x": 100 + offset, "y": 100},
                    {"x": 400 + offset, "y": 100},
                    {"x": 400 + offset, "y": 400},
                    {"x": 100 + offset, "y": 400},
                ],
            }
        ],
    }


def test_roi_config_is_versioned_and_previous_version_can_be_approved(
    client: TestClient,
) -> None:
    endpoint = "/api/stores/store-001/cameras/roi-test-cam/roi-config"

    first = client.put(endpoint, json=_payload()).json()
    second = client.put(endpoint, json=_payload(source="ai_assisted", offset=20)).json()

    assert first["version"] == 1
    assert second["version"] == 2
    assert second["status"] == "approved"

    history = client.get(f"{endpoint}s").json()
    assert [item["version"] for item in history] == [2, 1]
    assert [item["status"] for item in history] == ["approved", "archived"]

    restored = client.post(f"{endpoint}s/1/approve").json()
    assert restored["version"] == 1
    assert restored["status"] == "approved"
    assert client.get(endpoint).json()["version"] == 1


def test_internal_roi_endpoint_returns_only_approved_config(
    client: TestClient,
) -> None:
    public_endpoint = "/api/stores/store-002/cameras/roi-internal-cam/roi-config"
    client.put(public_endpoint, json=_payload())

    response = client.get(
        "/internal/stores/store-002/cameras/roi-internal-cam/roi-config"
    )

    assert response.status_code == 200
    assert response.json()["store_id"] == "store-002"


def test_self_intersecting_roi_polygon_is_rejected(client: TestClient) -> None:
    payload = _payload()
    payload["zones"][0]["polygon"] = [
        {"x": 100, "y": 100},
        {"x": 400, "y": 400},
        {"x": 100, "y": 400},
        {"x": 400, "y": 100},
    ]

    response = client.put(
        "/api/stores/store-001/cameras/roi-invalid-cam/roi-config",
        json=payload,
    )

    assert response.status_code == 422


def test_unknown_store_roi_config_is_rejected(client: TestClient) -> None:
    response = client.put(
        "/api/stores/store-999/cameras/cam-1/roi-config",
        json=_payload(),
    )

    assert response.status_code == 404
