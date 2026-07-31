"""주문 이벤트를 주문 단위 CSV로 변환한다."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from .models import OrderEvent, OrderStatus


KST = ZoneInfo("Asia/Seoul")
CSV_FIELDS = [
    "simulation_run_id",
    "data_source",
    "order_id",
    "store_id",
    "final_status",
    "order_date_kst",
    "received_at_kst",
    "preparing_at_kst",
    "ready_at_kst",
    "completed_at_kst",
    "queue_to_preparing_seconds",
    "preparation_seconds",
    "pickup_wait_seconds",
    "total_lead_time_seconds",
    "total_item_quantity",
    "items",
]


def build_order_export_csv(events: list[OrderEvent]) -> str:
    """상태 이벤트를 주문 한 건당 한 행인 UTF-8 BOM CSV로 만든다."""
    grouped: dict[tuple[str, str], list[OrderEvent]] = defaultdict(list)
    for event in events:
        grouped[(event.store_id, event.order_id)].append(event)

    rows = [
        _build_order_row(order_events)
        for order_events in grouped.values()
    ]
    rows.sort(
        key=lambda row: (
            row["received_at_kst"],
            row["store_id"],
            row["order_id"],
        )
    )

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return "\ufeff" + output.getvalue()


def _build_order_row(events: list[OrderEvent]) -> dict[str, str | int | float]:
    ordered = sorted(events, key=lambda event: (event.occurred_at, event.event_id))
    first = ordered[0]
    status_times: dict[OrderStatus, datetime] = {}
    for event in ordered:
        status_times.setdefault(event.status, event.occurred_at)

    received_at = status_times.get(OrderStatus.RECEIVED)
    preparing_at = status_times.get(OrderStatus.PREPARING)
    ready_at = status_times.get(OrderStatus.READY)
    completed_at = status_times.get(OrderStatus.COMPLETED)
    item_source = next(
        (event for event in ordered if event.status == OrderStatus.RECEIVED),
        first,
    )
    item_quantities: dict[tuple[str, str], int] = defaultdict(int)
    for item in item_source.items:
        name = item.name or item.menu_id
        item_quantities[(name, item.menu_id)] += item.quantity

    return {
        "simulation_run_id": _simulation_run_id(first.order_id, first.store_id),
        "data_source": (
            "synthetic_order_simulator"
            if first.order_id.startswith("sim-")
            else "order_event"
        ),
        "order_id": first.order_id,
        "store_id": first.store_id,
        "final_status": ordered[-1].status.value,
        "order_date_kst": _format_date(received_at or first.occurred_at),
        "received_at_kst": _format_datetime(received_at),
        "preparing_at_kst": _format_datetime(preparing_at),
        "ready_at_kst": _format_datetime(ready_at),
        "completed_at_kst": _format_datetime(completed_at),
        "queue_to_preparing_seconds": _elapsed_seconds(received_at, preparing_at),
        "preparation_seconds": _elapsed_seconds(preparing_at, ready_at),
        "pickup_wait_seconds": _elapsed_seconds(ready_at, completed_at),
        "total_lead_time_seconds": _elapsed_seconds(received_at, completed_at),
        "total_item_quantity": sum(item_quantities.values()),
        "items": " | ".join(
            f"{name} x{quantity}"
            for (name, _), quantity in sorted(item_quantities.items())
        ),
    }


def _simulation_run_id(order_id: str, store_id: str) -> str:
    if not order_id.startswith("sim-"):
        return ""
    marker = f"-{store_id}-"
    value = order_id.removeprefix("sim-")
    if marker not in value:
        return ""
    return value.rsplit(marker, 1)[0]


def _format_date(value: datetime) -> str:
    return value.astimezone(KST).date().isoformat()


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(KST).isoformat(timespec="milliseconds")


def _elapsed_seconds(
    start: datetime | None,
    end: datetime | None,
) -> str | float:
    if start is None or end is None:
        return ""
    return round((end - start).total_seconds(), 1)
