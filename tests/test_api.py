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


def test_menus_are_filtered_by_store(client: TestClient) -> None:
    store_one_response = client.get("/api/stores/store-001/menus")
    store_two_response = client.get("/api/stores/store-002/menus")

    assert store_one_response.status_code == 200
    assert store_two_response.status_code == 200
    assert store_one_response.json()["menus"]
    assert store_two_response.json()["menus"]
    assert all(
        menu["store_id"] == "store-001"
        for menu in store_one_response.json()["menus"]
    )
    assert all(
        menu["store_id"] == "store-002"
        for menu in store_two_response.json()["menus"]
    )


def test_policies_are_filtered_by_store(client: TestClient) -> None:
    store_one_response = client.get("/api/stores/store-001/policies")
    store_two_response = client.get("/api/stores/store-002/policies")

    assert store_one_response.status_code == 200
    assert store_two_response.status_code == 200
    assert store_one_response.json()["policies"]
    assert store_two_response.json()["policies"]
    assert all(
        policy["store_id"] == "store-001"
        for policy in store_one_response.json()["policies"]
    )
    assert all(
        policy["store_id"] == "store-002"
        for policy in store_two_response.json()["policies"]
    )


def test_unknown_store_has_empty_menu_and_policy_lists(
    client: TestClient,
) -> None:
    menu_response = client.get("/api/stores/store-does-not-exist/menus")
    policy_response = client.get(
        "/api/stores/store-does-not-exist/policies"
    )

    assert menu_response.status_code == 200
    assert menu_response.json()["menus"] == []
    assert policy_response.status_code == 200
    assert policy_response.json()["policies"] == []


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


def test_same_order_id_is_read_separately_by_store(client: TestClient) -> None:
    store_one_event = {
        "event_id": "event-shared-order-store-001",
        "order_id": "shared-order",
        "store_id": "store-001",
        "occurred_at": "2026-07-20T11:00:00+09:00",
        "status": "received",
        "items": [{"menu_id": "menu-001", "quantity": 1}],
    }
    store_two_event = {
        **store_one_event,
        "event_id": "event-shared-order-store-002",
        "store_id": "store-002",
        "occurred_at": "2026-07-20T11:05:00+09:00",
        "status": "ready",
    }

    client.post("/internal/order-events", json=store_one_event)
    client.post("/internal/order-events", json=store_two_event)

    store_one_response = client.get(
        "/api/stores/store-001/orders/shared-order"
    )
    store_two_response = client.get(
        "/api/stores/store-002/orders/shared-order"
    )

    assert store_one_response.status_code == 200
    assert store_one_response.json()["store_id"] == "store-001"
    assert store_one_response.json()["status"] == "received"
    assert store_two_response.status_code == 200
    assert store_two_response.json()["store_id"] == "store-002"
    assert store_two_response.json()["status"] == "ready"


def test_missing_store_order_pair_returns_404(client: TestClient) -> None:
    response = client.get(
        "/api/stores/store-does-not-exist/orders/order-does-not-exist"
    )

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
