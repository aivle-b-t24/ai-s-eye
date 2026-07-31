"""여러 매장의 상태와 주문 이력을 슈퍼바이저용 수치로 집계한다."""

from collections import defaultdict
from datetime import datetime, timezone

from .models import (
    MenuItemSummary,
    OrderDataSource,
    OrderEvent,
    OrderStatus,
    OrderStatusCounts,
    OrderSummary,
    QualityStatus,
    StoreOperatingSummary,
    StoreState,
    StoreSummaryResponse,
    SummaryPeriod,
    TrafficSummary,
    VideoSummary,
)


TOP_MENU_LIMIT = 5


def build_store_summary(
    states: list[StoreState],
    orders: list[OrderEvent],
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> StoreSummaryResponse:
    """기간에 포함된 이력을 매장별로 묶어 사실 기반 요약을 만든다."""
    states_by_store: dict[str, list[StoreState]] = defaultdict(list)
    orders_by_store: dict[str, list[OrderEvent]] = defaultdict(list)

    for state in states:
        states_by_store[state.store_id].append(state)
    for order in orders:
        orders_by_store[order.store_id].append(order)

    store_ids = sorted(set(states_by_store) | set(orders_by_store))
    observed_times = [state.captured_at for state in states] + [
        order.occurred_at for order in orders
    ]
    period = SummaryPeriod(
        start_at=start_at if start_at is not None else _minimum(observed_times),
        end_at=end_at if end_at is not None else _maximum(observed_times),
    )

    stores = [
        StoreOperatingSummary(
            store_id=store_id,
            traffic_summary=_traffic_summary(states_by_store[store_id]),
            order_summary=_order_summary(orders_by_store[store_id]),
            video_summary=_video_summary(states_by_store[store_id]),
        )
        for store_id in store_ids
    ]

    return StoreSummaryResponse(
        generated_at=datetime.now(timezone.utc),
        data_source="postgresql",
        period=period,
        stores=stores,
    )


def _traffic_summary(states: list[StoreState]) -> TrafficSummary | None:
    if not states:
        return None

    latest = max(states, key=lambda state: state.captured_at)
    peak_person = max(
        states,
        key=lambda state: (
            state.visible_person_count,
            state.captured_at,
        ),
    )
    peak_queue = max(
        states,
        key=lambda state: (
            state.queue_count_estimate,
            state.captured_at,
        ),
    )
    count = len(states)

    return TrafficSummary(
        observation_count=count,
        latest_captured_at=latest.captured_at,
        latest_visible_person_count=latest.visible_person_count,
        latest_queue_count_estimate=latest.queue_count_estimate,
        average_visible_person_count=round(
            sum(state.visible_person_count for state in states) / count,
            2,
        ),
        average_queue_count_estimate=round(
            sum(state.queue_count_estimate for state in states) / count,
            2,
        ),
        peak_visible_person_count=peak_person.visible_person_count,
        peak_visible_person_count_at=peak_person.captured_at,
        peak_queue_count_estimate=peak_queue.queue_count_estimate,
        peak_queue_count_estimate_at=peak_queue.captured_at,
    )


def _order_summary(orders: list[OrderEvent]) -> OrderSummary:
    received_order_ids = {
        event.order_id
        for event in orders
        if event.status == OrderStatus.RECEIVED
    }
    relevant_orders = [
        event for event in orders if event.order_id in received_order_ids
    ]
    latest_by_order: dict[str, OrderEvent] = {}
    for event in sorted(
        relevant_orders,
        key=lambda item: (item.occurred_at, item.event_id),
    ):
        latest_by_order[event.order_id] = event

    status_counts = {status.value: 0 for status in OrderStatus}
    menu_quantities: dict[str, int] = defaultdict(int)
    menu_names: dict[str, str | None] = {}

    for event in latest_by_order.values():
        status_counts[event.status.value] += 1
        if event.status in {OrderStatus.CANCELLED, OrderStatus.REJECTED}:
            continue
        for item in event.items:
            menu_quantities[item.menu_id] += item.quantity
            if item.name is not None or item.menu_id not in menu_names:
                menu_names[item.menu_id] = item.name

    top_menu_items = [
        MenuItemSummary(
            menu_id=menu_id,
            name=menu_names.get(menu_id),
            quantity=quantity,
        )
        for menu_id, quantity in sorted(
            menu_quantities.items(),
            key=lambda value: (-value[1], value[0]),
        )[:TOP_MENU_LIMIT]
    ]

    return OrderSummary(
        total_order_count=len(latest_by_order),
        order_event_count=len(relevant_orders),
        data_sources=sorted(
            {
                _order_data_source(order_id)
                for order_id in latest_by_order
            },
            key=lambda source: source.value,
        ),
        latest_status_counts=OrderStatusCounts(**status_counts),
        top_menu_items=top_menu_items,
    )


def _order_data_source(order_id: str) -> OrderDataSource:
    if order_id.startswith("sim-"):
        return OrderDataSource.SYNTHETIC_ORDER_SIMULATOR
    return OrderDataSource.ORDER_EVENT


def _video_summary(states: list[StoreState]) -> VideoSummary | None:
    if not states:
        return None

    latest = max(states, key=lambda state: state.captured_at)
    return VideoSummary(
        latest_quality_status=latest.quality_status,
        quality_issue_count=sum(
            state.quality_status != QualityStatus.NORMAL
            for state in states
        ),
    )


def _minimum(values: list[datetime]) -> datetime | None:
    return min(values) if values else None


def _maximum(values: list[datetime]) -> datetime | None:
    return max(values) if values else None
