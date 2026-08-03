"""매장 상태와 주문 이벤트를 시간대별 운영 지표로 집계한다."""

from datetime import datetime, timedelta, timezone
from math import ceil

from .models import (
    OrderEvent,
    OrderStatus,
    QualityStatus,
    StoreState,
    StoreTimelinePoint,
    StoreTimelineResponse,
    SummaryPeriod,
)


TIMELINE_INTERVALS = {
    "1h": timedelta(hours=1),
    "1d": timedelta(days=1),
}


def build_store_timeline(
    store_id: str,
    states: list[StoreState],
    orders: list[OrderEvent],
    *,
    start_at: datetime,
    end_at: datetime,
    interval: str = "1h",
) -> StoreTimelineResponse:
    """요청 기간을 고정 간격으로 나눠 매장 운영 지표를 계산한다.

    각 구간은 ``start_at <= value < end_at`` 규칙을 사용한다. 주문 건수는
    상태 변경 이벤트 전체가 아니라 ``received`` 이벤트의 고유 주문번호를 센다.
    """
    interval_delta = TIMELINE_INTERVALS[interval]
    interval_seconds = interval_delta.total_seconds()
    duration_seconds = (
        end_at.astimezone(timezone.utc) - start_at.astimezone(timezone.utc)
    ).total_seconds()
    bucket_count = ceil(duration_seconds / interval_seconds)
    state_buckets: list[list[StoreState]] = [[] for _ in range(bucket_count)]
    order_buckets: list[list[OrderEvent]] = [[] for _ in range(bucket_count)]

    for state in states:
        if state.store_id != store_id:
            continue
        index = _bucket_index(
            state.captured_at,
            start_at,
            end_at,
            interval_seconds,
        )
        if index is not None:
            state_buckets[index].append(state)

    for order in orders:
        if order.store_id != store_id or order.status != OrderStatus.RECEIVED:
            continue
        index = _bucket_index(
            order.occurred_at,
            start_at,
            end_at,
            interval_seconds,
        )
        if index is not None:
            order_buckets[index].append(order)

    points = [
        _build_point(
            states=state_buckets[index],
            orders=order_buckets[index],
            start_at=start_at + (interval_delta * index),
            end_at=min(start_at + (interval_delta * (index + 1)), end_at),
        )
        for index in range(bucket_count)
    ]

    return StoreTimelineResponse(
        store_id=store_id,
        interval=interval,
        period=SummaryPeriod(start_at=start_at, end_at=end_at),
        points=points,
    )


def _bucket_index(
    value: datetime,
    start_at: datetime,
    end_at: datetime,
    interval_seconds: float,
) -> int | None:
    value_utc = value.astimezone(timezone.utc)
    start_utc = start_at.astimezone(timezone.utc)
    end_utc = end_at.astimezone(timezone.utc)
    if value_utc < start_utc or value_utc >= end_utc:
        return None
    return int((value_utc - start_utc).total_seconds() // interval_seconds)


def _build_point(
    *,
    states: list[StoreState],
    orders: list[OrderEvent],
    start_at: datetime,
    end_at: datetime,
) -> StoreTimelinePoint:
    observation_count = len(states)
    if observation_count:
        average_people = round(
            sum(state.visible_person_count for state in states) / observation_count,
            2,
        )
        peak_people = max(state.visible_person_count for state in states)
        average_queue = round(
            sum(state.queue_count_estimate for state in states) / observation_count,
            2,
        )
        peak_queue = max(state.queue_count_estimate for state in states)
    else:
        average_people = None
        peak_people = None
        average_queue = None
        peak_queue = None

    return StoreTimelinePoint(
        start_at=start_at,
        end_at=end_at,
        observation_count=observation_count,
        average_visible_person_count=average_people,
        peak_visible_person_count=peak_people,
        average_queue_count_estimate=average_queue,
        peak_queue_count_estimate=peak_queue,
        order_count=len({order.order_id for order in orders}),
        quality_issue_count=sum(
            state.quality_status != QualityStatus.NORMAL
            for state in states
        ),
    )
