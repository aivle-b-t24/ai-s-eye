import csv
import io
from datetime import datetime

from app.models import OrderEvent
from app.order_export import build_order_export_csv


def make_event(
    *,
    event_id: str,
    status: str,
    occurred_at: str,
) -> OrderEvent:
    return OrderEvent.model_validate(
        {
            "event_id": event_id,
            "order_id": "sim-seed-july-30d-store-001-000001",
            "store_id": "store-001",
            "occurred_at": occurred_at,
            "status": status,
            "items": [
                {"menu_id": "americano", "name": "아메리카노", "quantity": 2},
                {"menu_id": "latte", "name": "카페라떼", "quantity": 1},
            ],
        }
    )


def test_order_events_are_exported_as_one_order_row() -> None:
    events = [
        make_event(
            event_id="event-received",
            status="received",
            occurred_at="2026-07-01T09:00:00+09:00",
        ),
        make_event(
            event_id="event-preparing",
            status="preparing",
            occurred_at="2026-07-01T09:00:30+09:00",
        ),
        make_event(
            event_id="event-ready",
            status="ready",
            occurred_at="2026-07-01T09:02:00+09:00",
        ),
        make_event(
            event_id="event-completed",
            status="completed",
            occurred_at="2026-07-01T09:02:30+09:00",
        ),
    ]

    content = build_order_export_csv(events)
    rows = list(csv.DictReader(io.StringIO(content.removeprefix("\ufeff"))))

    assert content.startswith("\ufeff")
    assert len(rows) == 1
    assert rows[0]["simulation_run_id"] == "seed-july-30d"
    assert rows[0]["data_source"] == "synthetic_order_simulator"
    assert rows[0]["final_status"] == "completed"
    assert rows[0]["order_date_kst"] == "2026-07-01"
    assert rows[0]["queue_to_preparing_seconds"] == "30.0"
    assert rows[0]["preparation_seconds"] == "90.0"
    assert rows[0]["pickup_wait_seconds"] == "30.0"
    assert rows[0]["total_lead_time_seconds"] == "150.0"
    assert rows[0]["total_item_quantity"] == "3"
    assert rows[0]["items"] == "아메리카노 x2 | 카페라떼 x1"


def test_incomplete_order_keeps_unavailable_durations_empty() -> None:
    content = build_order_export_csv(
        [
            make_event(
                event_id="event-only-received",
                status="received",
                occurred_at="2026-07-02T10:00:00+09:00",
            )
        ]
    )
    row = next(csv.DictReader(io.StringIO(content.removeprefix("\ufeff"))))

    assert row["final_status"] == "received"
    assert row["preparing_at_kst"] == ""
    assert row["total_lead_time_seconds"] == ""
