from fastapi.testclient import TestClient


def _payload(*, offset: int = 0) -> dict:
    return {
        "coordinate_space": "normalized_1000",
        "image_size": {"width": 1920, "height": 1080},
        "source": "manual",
        "perspective": {
            "far_y": 240,
            "near_y": 960,
            "far_scale": 0.58,
            "near_scale": 1.42,
        },
        "seat_anchors": [
            {"id": "seat-1", "x": 260, "y": 440, "table_id": "table-1"},
        ],
        "objects": [
            {
                "id": "table-1",
                "type": "table",
                "label": "창가 테이블",
                "polygon": [
                    {"x": 100 + offset, "y": 100},
                    {"x": 400 + offset, "y": 100},
                    {"x": 400 + offset, "y": 400},
                    {"x": 100 + offset, "y": 400},
                ],
            },
            {
                "id": "table-1-front",
                "type": "occluder",
                "label": "",
                "polygon": [
                    {"x": 100 + offset, "y": 350},
                    {"x": 400 + offset, "y": 350},
                    {"x": 400 + offset, "y": 430},
                    {"x": 100 + offset, "y": 430},
                ],
            },
        ],
    }


def test_scene_config_is_versioned_and_previous_version_can_be_approved(
    client: TestClient,
) -> None:
    endpoint = "/api/stores/store-001/cameras/scene-test-cam/scene-config"

    first = client.put(endpoint, json=_payload()).json()
    second = client.put(endpoint, json=_payload(offset=20)).json()

    assert first["version"] == 1
    assert second["version"] == 2
    assert second["status"] == "approved"
    assert second["perspective"]["far_scale"] == 0.58
    assert second["seat_anchors"][0]["table_id"] == "table-1"

    history = client.get(f"{endpoint}s").json()
    assert [item["version"] for item in history] == [2, 1]
    assert [item["status"] for item in history] == ["approved", "archived"]

    restored = client.post(f"{endpoint}s/1/approve").json()
    assert restored["version"] == 1
    assert client.get(endpoint).json()["version"] == 1


def test_self_intersecting_scene_polygon_is_rejected(client: TestClient) -> None:
    payload = _payload()
    payload["objects"][0]["polygon"] = [
        {"x": 100, "y": 100},
        {"x": 400, "y": 400},
        {"x": 100, "y": 400},
        {"x": 400, "y": 100},
    ]

    response = client.put(
        "/api/stores/store-001/cameras/scene-invalid-cam/scene-config",
        json=payload,
    )

    assert response.status_code == 422


def test_scene_config_rejects_invalid_perspective(client: TestClient) -> None:
    payload = _payload()
    payload["perspective"]["far_y"] = 980
    payload["perspective"]["near_y"] = 500

    response = client.put(
        "/api/stores/store-001/cameras/scene-perspective-cam/scene-config",
        json=payload,
    )

    assert response.status_code == 422


def test_scene_config_rejects_unknown_seat_table(client: TestClient) -> None:
    payload = _payload()
    payload["seat_anchors"][0]["table_id"] = "missing-table"

    response = client.put(
        "/api/stores/store-001/cameras/scene-seat-cam/scene-config",
        json=payload,
    )

    assert response.status_code == 422
