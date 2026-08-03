from datetime import datetime, timedelta, timezone

import pytest

from app.models import (
    OrderEvent,
    OrderItem,
    OrderStatus,
    QualityStatus,
    StoreState,
)
from app.timeline import build_store_timeline


def _state(
    captured_at: datetime,
    people: int,
    queue: int,
    quality: QualityStatus = QualityStatus.NORMAL,
) -> StoreState:
    return StoreState(
        store_id="store-001",
        camera_id="cam-timeline",
        captured_at=captured_at,
        visible_person_count=people,
        queue_count_estimate=queue,
        zone_counts={"waiting": queue},
        quality_status=quality,
        source="pytest",
        model_version="test-v1",
    )


def _order(
    order_id: str,
    occurred_at: datetime,
    status: OrderStatus,
) -> OrderEvent:
    return OrderEvent(
        event_id=f"{order_id}-{status.value}",
        order_id=order_id,
        store_id="store-001",
        occurred_at=occurred_at,
        status=status,
        items=[OrderItem(menu_id="menu-001", name="아메리카노", quantity=1)],
    )


def test_build_store_timeline_groups_metrics_and_keeps_empty_buckets() -> None:
    start_at = datetime(2026, 7, 28, 10, 15, tzinfo=timezone.utc)
    end_at = start_at + timedelta(hours=2, minutes=30)
    states = [
        _state(start_at + timedelta(minutes=5), 4, 1),
        _state(
            start_at + timedelta(minutes=25),
            8,
            3,
            QualityStatus.LOW,
        ),
        _state(start_at + timedelta(hours=1, minutes=15), 6, 2),
        _state(end_at, 99, 99),
    ]
    orders = [
        _order("order-001", start_at + timedelta(minutes=10), OrderStatus.RECEIVED),
        _order("order-001", start_at + timedelta(hours=1), OrderStatus.READY),
        _order("order-002", start_at + timedelta(hours=2, minutes=5), OrderStatus.RECEIVED),
    ]

    response = build_store_timeline(
        "store-001",
        states,
        orders,
        start_at=start_at,
        end_at=end_at,
    )

    assert len(response.points) == 3
    first, second, third = response.points
    assert first.observation_count == 2
    assert first.average_visible_person_count == 6
    assert first.peak_visible_person_count == 8
    assert first.average_queue_count_estimate == 2
    assert first.peak_queue_count_estimate == 3
    assert first.order_count == 1
    assert first.quality_issue_count == 1
    assert second.observation_count == 1
    assert second.order_count == 0
    assert third.observation_count == 0
    assert third.average_visible_person_count is None
    assert third.peak_queue_count_estimate is None
    assert third.order_count == 1
    assert third.end_at == end_at


@pytest.mark.parametrize(
    ("duration", "expected_points"),
    [
        (timedelta(hours=24), 24),
        (timedelta(days=7), 168),
        (timedelta(days=30), 720),
    ],
)
def test_build_store_timeline_supports_dashboard_periods(
    duration: timedelta,
    expected_points: int,
) -> None:
    start_at = datetime(2026, 7, 1, tzinfo=timezone.utc)

    response = build_store_timeline(
        "store-001",
        [],
        [],
        start_at=start_at,
        end_at=start_at + duration,
    )

    assert len(response.points) == expected_points
    assert all(point.observation_count == 0 for point in response.points)


def test_daily_timeline_uses_kst_boundaries_and_keeps_empty_days() -> None:
    kst = timezone(timedelta(hours=9))
    start_at = datetime(2026, 7, 1, tzinfo=kst)
    end_at = datetime(2026, 7, 4, tzinfo=kst)
    orders = [
        _order(
            "order-first-day",
            datetime(2026, 7, 1, 23, 59, tzinfo=kst),
            OrderStatus.RECEIVED,
        ),
        _order(
            "order-third-day",
            datetime(2026, 7, 3, 0, 0, tzinfo=kst),
            OrderStatus.RECEIVED,
        ),
        _order(
            "order-at-exclusive-end",
            end_at,
            OrderStatus.RECEIVED,
        ),
    ]

    response = build_store_timeline(
        "store-001",
        [],
        orders,
        start_at=start_at,
        end_at=end_at,
        interval="1d",
    )

    assert response.interval == "1d"
    assert len(response.points) == 3
    assert [point.order_count for point in response.points] == [1, 0, 1]
    assert response.points[0].start_at == start_at
    assert response.points[-1].end_at == end_at


def test_timeline_reports_waiting_order_queue_from_lifecycle() -> None:
    start_at = datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc)
    end_at = start_at + timedelta(hours=2)
    # 첫 시간대에 겹치는 두 주문(대기 2건 피크), 둘째 시간대는 주문 없음.
    orders = [
        _order("order-a", start_at + timedelta(minutes=0), OrderStatus.RECEIVED),
        _order("order-a", start_at + timedelta(minutes=30), OrderStatus.COMPLETED),
        _order("order-b", start_at + timedelta(minutes=15), OrderStatus.RECEIVED),
        _order("order-b", start_at + timedelta(minutes=45), OrderStatus.COMPLETED),
    ]

    response = build_store_timeline(
        "store-001",
        [],
        orders,
        start_at=start_at,
        end_at=end_at,
    )

    first, second = response.points
    assert first.peak_waiting_order_count == 2
    assert first.average_waiting_order_count == 1.0
    assert second.peak_waiting_order_count == 0
    assert second.average_waiting_order_count == 0.0
