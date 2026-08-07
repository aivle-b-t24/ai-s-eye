from typing import Any, Callable

import httpx

from aicc.client import StoreApiClient
from aicc.tools import StoreTools


def store_state_body(store_id: str = "store-001") -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "store_id": store_id,
        "camera_id": "cam-01",
        "captured_at": "2026-07-15T10:30:00+09:00",
        "visible_person_count": 5,
        "queue_count_estimate": 2,
        "zone_counts": {"waiting": 2, "seating": 3},
        "quality_status": "normal",
        "source": "mock",
        "model_version": "mock-v1",
    }


def menus_body() -> dict[str, Any]:
    return {
        "store_id": "store-001",
        "data_source": "mock",
        "menus": [
            {
                "menu_id": "americano",
                "category": "coffee",
                "name": "아메리카노",
                "price": 4500,
                "prep_minutes": 3,
                "available": True,
                "sold_out_reason": None,
            },
            {
                "menu_id": "cheesecake",
                "category": "dessert",
                "name": "치즈케이크",
                "price": 6000,
                "prep_minutes": 2,
                "available": False,
                "sold_out_reason": "금일 판매 종료",
            },
        ],
    }


def tools_for(handler: Callable[[httpx.Request], httpx.Response]) -> StoreTools:
    return StoreTools(StoreApiClient(transport=httpx.MockTransport(handler)))


def responder(status_code: int, body: Any) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=body)

    return handler


def test_store_state_returns_counts() -> None:
    with tools_for(responder(200, store_state_body())) as tools:
        result = tools.get_store_state()

    assert result["ok"] is True
    assert result["store_id"] == "store-001"
    assert result["visible_person_count"] == 5
    assert result["queue_count_estimate"] == 2
    assert result["quality_status"] == "normal"


def test_store_state_uses_requested_store_id() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json=store_state_body("store-042"))

    with tools_for(handler) as tools:
        tools.get_store_state("store-042")

    assert seen == ["/api/stores/store-042/state"]


def test_missing_store_state_reports_not_found() -> None:
    with tools_for(responder(404, {"detail": "Store state not found"})) as tools:
        result = tools.get_store_state("store-none")

    assert result["ok"] is False
    assert result["error"] == "store_not_found"
    assert result["message"]


def test_eta_returns_minutes() -> None:
    body = {
        "store_id": "store-001",
        "estimated_wait_minutes": 6,
        "calculation": "queue_count_estimate * 3",
        "data_source": "mock_rule",
    }

    with tools_for(responder(200, body)) as tools:
        result = tools.get_eta()

    assert result["ok"] is True
    assert result["estimated_wait_minutes"] == 6
    assert result["data_source"] == "mock_rule"
    # 응답에 waiting_order_count가 없으면 결과에도 넣지 않는다(그래도 ok=True).
    assert "waiting_order_count" not in result


def test_eta_includes_waiting_order_count_when_present() -> None:
    """사이트 '대기 주문'과 같은 값(waiting_order_count)이 응답에 있으면 그대로 담는다."""
    body = {
        "store_id": "store-001",
        "estimated_wait_minutes": 6,
        "data_source": "mock_rule",
        "waiting_order_count": 3,
    }

    with tools_for(responder(200, body)) as tools:
        result = tools.get_eta()

    assert result["ok"] is True
    assert result["waiting_order_count"] == 3


def test_menus_return_all_items_when_no_name_given() -> None:
    with tools_for(responder(200, menus_body())) as tools:
        result = tools.get_menus()

    assert result["ok"] is True
    assert len(result["menus"]) == 2


def test_menu_name_filter_reports_sold_out_item() -> None:
    with tools_for(responder(200, menus_body())) as tools:
        result = tools.get_menus(menu_name="치즈 케이크")

    assert result["ok"] is True
    assert len(result["menus"]) == 1
    assert result["menus"][0]["available"] is False
    assert result["menus"][0]["sold_out_reason"] == "금일 판매 종료"


def test_unknown_menu_name_returns_empty_list_with_message() -> None:
    with tools_for(responder(200, menus_body())) as tools:
        result = tools.get_menus(menu_name="붕어빵")

    assert result["ok"] is True
    assert result["menus"] == []
    assert "붕어빵" in result["message"]


def test_policies_return_title_and_content() -> None:
    body = {
        "store_id": "store-001",
        "data_source": "mock",
        "policies": [
            {
                "policy_id": "parking",
                "category": "facility",
                "title": "주차",
                "content": "매장 이용 고객은 1시간 무료 주차가 가능합니다.",
                "keywords": ["주차"],
            }
        ],
    }

    with tools_for(responder(200, body)) as tools:
        result = tools.get_policies()

    assert result["ok"] is True
    assert result["policies"] == [
        {
            "policy_id": "parking",
            "title": "주차",
            "content": "매장 이용 고객은 1시간 무료 주차가 가능합니다.",
        }
    ]


def test_missing_sample_file_reports_sample_data_unavailable() -> None:
    with tools_for(responder(503, {"detail": "Sample data is unavailable"})) as tools:
        result = tools.get_menus()

    assert result["ok"] is False
    assert result["error"] == "sample_data_unavailable"


def test_connection_failure_reports_api_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with tools_for(handler) as tools:
        result = tools.get_eta()

    assert result["ok"] is False
    assert result["error"] == "api_unavailable"


def test_unexpected_body_reports_unexpected_response() -> None:
    with tools_for(responder(200, {"unexpected": "shape"})) as tools:
        result = tools.get_store_state()

    assert result["ok"] is False
    assert result["error"] == "unexpected_response"


def order_body(order_id: str = "order-001", status: str = "received") -> dict[str, Any]:
    return {
        "event_id": "event-001",
        "order_id": order_id,
        "store_id": "store-001",
        "occurred_at": "2026-07-20T10:31:00+09:00",
        "status": status,
        "items": [{"menu_id": "menu-001", "name": "아메리카노", "quantity": 2}],
    }


def test_order_status_received() -> None:
    with tools_for(responder(200, order_body(status="received"))) as tools:
        result = tools.get_order_status("order-001")

    assert result["ok"] is True
    assert result["order_id"] == "order-001"
    assert result["status"] == "received"
    assert "접수" in result["status_message"]
    assert result["items"][0]["name"] == "아메리카노"
    assert result["items"][0]["quantity"] == 2


def test_order_status_preparing() -> None:
    with tools_for(responder(200, order_body(status="preparing"))) as tools:
        result = tools.get_order_status("order-001")

    assert result["status"] == "preparing"
    assert "준비" in result["status_message"]


def test_order_status_ready() -> None:
    with tools_for(responder(200, order_body(status="ready"))) as tools:
        result = tools.get_order_status("order-001")

    assert result["status"] == "ready"
    assert "픽업" in result["status_message"] or "준비" in result["status_message"]


def test_order_status_all_six_statuses_have_message() -> None:
    for status in ("received", "preparing", "ready", "completed", "cancelled", "rejected"):
        with tools_for(responder(200, order_body(status=status))) as tools:
            result = tools.get_order_status("order-001")
        assert result["status_message"], f"{status} 안내 문장 없음"


def test_order_uses_requested_id_in_path() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json=order_body("order-042"))

    with tools_for(handler) as tools:
        tools.get_order_status("order-042")

    assert seen == ["/api/orders/order-042"]


def test_missing_order_reports_order_not_found() -> None:
    with tools_for(responder(404, {"detail": "Order not found"})) as tools:
        result = tools.get_order_status("order-999")

    assert result["ok"] is False
    assert result["error"] == "order_not_found"
    assert result["message"]


def test_order_api_error_reports_gracefully() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with tools_for(handler) as tools:
        result = tools.get_order_status("order-001")

    assert result["ok"] is False
    assert result["error"] == "api_unavailable"
