from datetime import datetime, timedelta, timezone

from app.models import (
    OrderEvent,
    OrderItem,
    OrderStatus,
    QualityStatus,
    StoreState,
)
from app.summary import build_store_summary


BASE_TIME = datetime(2026, 7, 22, 1, 0, tzinfo=timezone.utc)


def _state(
    store_id: str,
    hours: int,
    person_count: int,
    queue_count: int,
    quality_status: QualityStatus = QualityStatus.NORMAL,
) -> StoreState:
    return StoreState(
        store_id=store_id,
        camera_id="cam-summary",
        captured_at=BASE_TIME + timedelta(hours=hours),
        visible_person_count=person_count,
        queue_count_estimate=queue_count,
        zone_counts={"waiting": queue_count},
        quality_status=quality_status,
        source="pytest",
        model_version="test-v1",
    )


def _order(
    event_id: str,
    order_id: str,
    store_id: str,
    hours: int,
    status: OrderStatus,
    menu_id: str,
    name: str,
    quantity: int,
) -> OrderEvent:
    return OrderEvent(
        event_id=event_id,
        order_id=order_id,
        store_id=store_id,
        occurred_at=BASE_TIME + timedelta(hours=hours),
        status=status,
        items=[
            OrderItem(
                menu_id=menu_id,
                name=name,
                quantity=quantity,
            )
        ],
    )


def test_build_store_summary_calculates_two_store_metrics() -> None:
    states = [
        _state("store-001", 0, 8, 1),
        _state("store-001", 2, 28, 9, QualityStatus.LOW),
        _state("store-001", 4, 16, 2),
        _state("store-001", 6, 10, 0),
        _state("store-002", 0, 10, 0),
        _state("store-002", 2, 15, 2),
        _state("store-002", 4, 22, 4),
        _state("store-002", 6, 18, 1),
    ]
    orders = [
        _order(
            "event-001",
            "order-001",
            "store-001",
            1,
            OrderStatus.RECEIVED,
            "menu-001",
            "아메리카노",
            2,
        ),
        _order(
            "event-002",
            "order-001",
            "store-001",
            3,
            OrderStatus.READY,
            "menu-001",
            "아메리카노",
            2,
        ),
        _order(
            "event-003",
            "order-002",
            "store-001",
            3,
            OrderStatus.PREPARING,
            "menu-002",
            "카페라떼",
            1,
        ),
        _order(
            "event-004",
            "order-003",
            "store-002",
            4,
            OrderStatus.COMPLETED,
            "menu-021",
            "크루아상",
            3,
        ),
        _order(
            "event-005",
            "order-004",
            "store-002",
            5,
            OrderStatus.CANCELLED,
            "menu-999",
            "취소 메뉴",
            99,
        ),
    ]

    response = build_store_summary(states, orders)
    stores = {store.store_id: store for store in response.stores}
    store_one = stores["store-001"]
    store_two = stores["store-002"]

    assert response.period.start_at == BASE_TIME
    assert response.period.end_at == BASE_TIME + timedelta(hours=6)
    assert store_one.traffic_summary is not None
    assert store_one.traffic_summary.observation_count == 4
    assert store_one.traffic_summary.average_visible_person_count == 15.5
    assert store_one.traffic_summary.average_queue_count_estimate == 3
    assert store_one.traffic_summary.peak_visible_person_count == 28
    assert store_one.traffic_summary.peak_queue_count_estimate == 9
    assert store_one.order_summary.total_order_count == 2
    assert store_one.order_summary.order_event_count == 3
    assert store_one.order_summary.latest_status_counts.ready == 1
    assert store_one.order_summary.latest_status_counts.preparing == 1
    assert store_one.order_summary.top_menu_items[0].quantity == 2
    assert store_one.video_summary is not None
    assert store_one.video_summary.latest_quality_status == QualityStatus.NORMAL
    assert store_one.video_summary.quality_issue_count == 1

    assert store_two.traffic_summary is not None
    assert store_two.traffic_summary.average_visible_person_count == 16.25
    assert store_two.traffic_summary.average_queue_count_estimate == 1.75
    assert store_two.order_summary.total_order_count == 2
    assert store_two.order_summary.latest_status_counts.cancelled == 1
    assert store_two.order_summary.top_menu_items[0].menu_id == "menu-021"
    assert all(
        item.menu_id != "menu-999"
        for item in store_two.order_summary.top_menu_items
    )


def test_build_store_summary_returns_empty_store_list_without_data() -> None:
    response = build_store_summary([], [])

    assert response.period.start_at is None
    assert response.period.end_at is None
    assert response.stores == []
