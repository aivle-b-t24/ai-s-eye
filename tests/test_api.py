from fastapi.testclient import TestClient


def valid_store_state(store_id: str = "store-test") -> dict:
    return {
        "schema_version": "1.0",
        "store_id": store_id,
        "camera_id": "cam-test",
        "captured_at": "2026-07-15T10:30:00+09:00",
        "visible_person_count": 4,
        "queue_count_estimate": 2,
        "zone_counts": {"waiting": 2, "seating": 2},
        "quality_status": "normal",
        "source": "mock",
        "model_version": "mock-test-v1",
    }


def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] in {"ok", "degraded"}


def test_store_state_can_be_saved_and_read(client: TestClient) -> None:
    payload = valid_store_state()

    save_response = client.post("/internal/store-states", json=payload)
    read_response = client.get("/api/stores/store-test/state")

    assert save_response.status_code == 201
    assert save_response.json()["saved"] is True
    assert read_response.status_code == 200
    assert read_response.json()["visible_person_count"] == 4


def test_missing_store_state_returns_404(client: TestClient) -> None:
    response = client.get("/api/stores/store-does-not-exist/state")

    assert response.status_code == 404


def test_invalid_store_state_is_rejected(client: TestClient) -> None:
    payload = valid_store_state("invalid-store")
    payload["visible_person_count"] = -1

    response = client.post("/internal/store-states", json=payload)

    assert response.status_code == 422


def test_menu_sample_has_ten_items_and_two_sold_out(client: TestClient) -> None:
    response = client.get("/api/stores/store-001/menus")
    body = response.json()

    assert response.status_code == 200
    assert len(body["menus"]) >= 10
    assert sum(not menu["available"] for menu in body["menus"]) >= 2


def test_policy_sample_has_five_items(client: TestClient) -> None:
    response = client.get("/api/stores/store-001/policies")

    assert response.status_code == 200
    assert len(response.json()["policies"]) >= 5


def test_order_event_is_accepted(client: TestClient) -> None:
    payload = {
        "event_id": "event-test",
        "order_id": "order-test",
        "store_id": "store-001",
        "occurred_at": "2026-07-15T11:00:00+09:00",
        "status": "received",
        "items": [{"menu_id": "americano", "quantity": 1}],
    }

    response = client.post("/internal/order-events", json=payload)

    assert response.status_code == 202
    assert response.json()["accepted"] is True


def test_latest_order_event_can_be_read(client: TestClient) -> None:
    received_event = {
        "event_id": "event-order-status-received",
        "order_id": "order-status-test",
        "store_id": "store-001",
        "occurred_at": "2026-07-20T11:00:00+09:00",
        "status": "received",
        "items": [{"menu_id": "menu-001", "quantity": 1}],
    }
    ready_event = {
        **received_event,
        "event_id": "event-order-status-ready",
        "occurred_at": "2026-07-20T11:03:00+09:00",
        "status": "ready",
    }

    client.post("/internal/order-events", json=received_event)
    client.post("/internal/order-events", json=ready_event)
    response = client.get("/api/orders/order-status-test")

    assert response.status_code == 200
    assert response.json()["event_id"] == "event-order-status-ready"
    assert response.json()["status"] == "ready"


def test_missing_order_returns_404(client: TestClient) -> None:
    response = client.get("/api/orders/order-does-not-exist")

    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found"


def test_invalid_order_status_is_rejected(client: TestClient) -> None:
    payload = {
        "event_id": "event-invalid",
        "order_id": "order-invalid",
        "store_id": "store-001",
        "occurred_at": "2026-07-15T11:00:00+09:00",
        "status": "unknown-status",
        "items": [{"menu_id": "americano", "quantity": 1}],
    }

    response = client.post("/internal/order-events", json=payload)

    assert response.status_code == 422
