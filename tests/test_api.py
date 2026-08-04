import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import default_summary_period, repository


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


def test_registered_store_without_state_returns_empty_snapshot(
    client: TestClient,
) -> None:
    created = repository.create_store("빈상태점")
    store_id = created.id
    try:
        state_response = client.get(f"/api/stores/{store_id}/state")
        eta_response = client.get(f"/api/stores/{store_id}/eta")

        assert state_response.status_code == 200
        body = state_response.json()
        assert body["store_id"] == store_id
        assert body["visible_person_count"] == 0
        assert body["source"] == "empty"
        assert eta_response.status_code == 200
        assert eta_response.json()["estimated_wait_minutes"] == 0
        assert eta_response.json()["data_source"] == "empty"
    finally:
        # 다른 테스트의 다음 store_id 발급을 오염시키지 않도록 정리한다.
        repository.delete_store(store_id)


def test_internal_stores_returns_master_with_names(client: TestClient) -> None:
    """서비스용 /internal/stores는 매장 마스터(ID+표시명)를 반환한다. AICC 챗봇이 씀."""
    response = client.get("/internal/stores")

    assert response.status_code == 200
    stores = {item["store_id"]: item["name"] for item in response.json()["stores"]}
    assert stores.get("store-001") == "동명점"
    assert stores.get("store-002") == "수완점"


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


def test_store_summary_requires_postgresql(client: TestClient) -> None:
    response = client.get("/api/stores/summary")

    assert response.status_code == 503
    assert response.json()["detail"] == "PostgreSQL is required for store summary"


def test_default_store_summary_period_is_recent_24_hours() -> None:
    now = datetime(2026, 7, 27, 1, 0, tzinfo=timezone.utc)

    start_at, end_at = default_summary_period(now)

    assert end_at == now
    assert end_at - start_at == timedelta(hours=24)


def test_store_summary_period_requires_both_boundaries(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/stores/summary",
        params={"start_at": "2026-07-22T00:00:00+09:00"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "start_at and end_at must be provided together"
    )


def test_store_summary_rejects_reversed_period(client: TestClient) -> None:
    response = client.get(
        "/api/stores/summary",
        params={
            "start_at": "2026-07-22T12:00:00+09:00",
            "end_at": "2026-07-22T10:00:00+09:00",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "start_at must be earlier than end_at"


def test_store_timeline_requires_postgresql(client: TestClient) -> None:
    response = client.get(
        "/api/stores/store-001/timeline",
        params={
            "start_at": "2026-07-22T00:00:00+09:00",
            "end_at": "2026-07-23T00:00:00+09:00",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "PostgreSQL is required for store timeline"


def test_store_timeline_requires_timezone(client: TestClient) -> None:
    response = client.get(
        "/api/stores/store-001/timeline",
        params={
            "start_at": "2026-07-22T00:00:00",
            "end_at": "2026-07-23T00:00:00",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "start_at and end_at must include a timezone"


def test_store_timeline_rejects_reversed_period(client: TestClient) -> None:
    response = client.get(
        "/api/stores/store-001/timeline",
        params={
            "start_at": "2026-07-23T00:00:00+09:00",
            "end_at": "2026-07-22T00:00:00+09:00",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "start_at must be earlier than end_at"


def test_store_timeline_rejects_period_over_31_days(client: TestClient) -> None:
    response = client.get(
        "/api/stores/store-001/timeline",
        params={
            "start_at": "2026-06-01T00:00:00+09:00",
            "end_at": "2026-07-03T00:00:00+09:00",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "timeline period must not exceed 31 days"


def test_store_timeline_rejects_unknown_interval(client: TestClient) -> None:
    response = client.get(
        "/api/stores/store-001/timeline",
        params={
            "start_at": "2026-07-22T00:00:00+09:00",
            "end_at": "2026-07-23T00:00:00+09:00",
            "interval": "1w",
        },
    )

    assert response.status_code == 422


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


def test_orders_can_be_downloaded_as_csv(client: TestClient) -> None:
    order_id = "sim-api-export-test-store-001-000001"
    base_event = {
        "order_id": order_id,
        "store_id": "store-001",
        "items": [{"menu_id": "americano", "name": "아메리카노", "quantity": 1}],
    }
    for event_id, status_name, occurred_at in [
        ("export-received", "received", "2026-07-29T10:00:00+09:00"),
        ("export-completed", "completed", "2026-07-29T10:03:00+09:00"),
    ]:
        response = client.post(
            "/internal/order-events",
            json={
                **base_event,
                "event_id": event_id,
                "status": status_name,
                "occurred_at": occurred_at,
            },
        )
        assert response.status_code == 202

    response = client.get(
        "/api/exports/orders.csv",
        params={
            "start_at": "2026-07-29T00:00:00+09:00",
            "end_at": "2026-07-30T00:00:00+09:00",
            "store_id": "store-001",
        },
    )
    rows = list(
        csv.DictReader(io.StringIO(response.content.decode("utf-8-sig")))
    )
    exported = next(row for row in rows if row["order_id"] == order_id)

    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == (
        'attachment; filename="orders_2026-07-29_2026-07-29.csv"'
    )
    assert exported["simulation_run_id"] == "api-export-test"
    assert exported["final_status"] == "completed"


def test_order_csv_export_requires_timezones(client: TestClient) -> None:
    response = client.get(
        "/api/exports/orders.csv",
        params={
            "start_at": "2026-07-01T00:00:00",
            "end_at": "2026-07-31T00:00:00",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "start_at and end_at must include a timezone"
    )


def test_order_csv_export_rejects_period_over_31_days(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/exports/orders.csv",
        params={
            "start_at": "2026-06-01T00:00:00+09:00",
            "end_at": "2026-07-03T00:00:00+09:00",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "order export period must not exceed 31 days"
    )


def test_store_settings_default_for_unset_store(client: TestClient) -> None:
    response = client.get("/api/stores/store-001/settings")
    assert response.status_code == 200
    assert response.json()["max_capacity"] == 30  # 기본 수용 인원


def test_store_settings_save_and_read(client: TestClient) -> None:
    put_response = client.put(
        "/api/stores/store-002/settings", json={"max_capacity": 25}
    )
    assert put_response.status_code == 200
    assert put_response.json()["max_capacity"] == 25

    read_response = client.get("/api/stores/store-002/settings")
    assert read_response.status_code == 200
    assert read_response.json()["max_capacity"] == 25


def test_store_settings_rejects_unknown_store(client: TestClient) -> None:
    response = client.put(
        "/api/stores/store-unknown/settings", json={"max_capacity": 20}
    )
    assert response.status_code == 422
