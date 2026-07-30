import asyncio
from datetime import date, datetime
import random
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app.models import OrderStatus
from app.order_simulator import (
    KST,
    MenuOption,
    OrderApiClient,
    _build_parser,
    create_order_plan,
    generate_seed_events,
    materialize_order_events,
    parse_available_menus,
    send_event_with_retry,
)


def _menus(store_id: str) -> list[MenuOption]:
    return [
        MenuOption(
            menu_id=f"{store_id}-americano",
            name="아메리카노",
            prep_minutes=3,
        ),
        MenuOption(
            menu_id=f"{store_id}-latte",
            name="카페라떼",
            prep_minutes=4,
        ),
    ]


def test_available_menus_excludes_other_store_and_sold_out_items() -> None:
    payload = {
        "menus": [
            {
                "store_id": "store-001",
                "menu_id": "menu-001",
                "name": "아메리카노",
                "prep_minutes": 3,
                "available": True,
            },
            {
                "store_id": "store-001",
                "menu_id": "menu-002",
                "name": "품절 라떼",
                "prep_minutes": 4,
                "available": False,
            },
            {
                "store_id": "store-002",
                "menu_id": "menu-003",
                "name": "다른 매장 메뉴",
                "prep_minutes": 2,
                "available": True,
            },
        ]
    }

    menus = parse_available_menus(payload, "store-001")

    assert menus == [
        MenuOption(menu_id="menu-001", name="아메리카노", prep_minutes=3.0)
    ]


def test_order_plan_uses_one_or_two_available_menus_and_keeps_items() -> None:
    plan = create_order_plan(
        store_id="store-001",
        run_id="test-run",
        sequence=1,
        menus=_menus("store-001"),
        rng=random.Random(7),
    )
    received_at = datetime(2026, 7, 30, 10, 0, tzinfo=KST)

    events = materialize_order_events(plan, received_at)

    assert [event.status for event in events] == [
        OrderStatus.RECEIVED,
        OrderStatus.PREPARING,
        OrderStatus.READY,
        OrderStatus.COMPLETED,
    ]
    assert (
        events[1].occurred_at - events[0].occurred_at
    ).total_seconds() == pytest.approx(15)
    assert (
        events[-1].occurred_at - events[-2].occurred_at
    ).total_seconds() == pytest.approx(60)
    assert 1 <= len(events[0].items) <= 2
    assert all(event.items == events[0].items for event in events)
    assert all(item.menu_id.startswith("store-001-") for item in events[0].items)
    assert events[0].order_id == "sim-test-run-store-001-000001"
    assert events[0].event_id.endswith("-received")


def test_seed_generation_is_deterministic_and_separates_stores() -> None:
    arguments = {
        "menus_by_store": {
            "store-001": _menus("store-001"),
            "store-002": _menus("store-002"),
        },
        "run_id": "seed-test",
        "days": 1,
        "end_date": date(2026, 7, 29),
        "seed": 1234,
    }

    first = generate_seed_events(**arguments)
    second = generate_seed_events(**arguments)

    assert [event.model_dump(mode="json") for event in first] == [
        event.model_dump(mode="json") for event in second
    ]
    assert first
    assert all(event.occurred_at.tzinfo is not None for event in first)
    assert all(
        event.occurred_at.astimezone(KST).date() == date(2026, 7, 29)
        for event in first
    )
    assert len(first) % 4 == 0

    for event in first:
        if event.store_id == "store-001":
            assert all(item.menu_id.startswith("store-001-") for item in event.items)
        else:
            assert all(item.menu_id.startswith("store-002-") for item in event.items)


def test_seed_requires_apply_before_persisting() -> None:
    parser = _build_parser()

    preview = parser.parse_args(["seed", "--days", "7"])
    applied = parser.parse_args(["seed", "--days", "7", "--apply"])

    assert preview.apply is False
    assert applied.apply is True


def test_retry_sends_the_same_event_id_until_success() -> None:
    attempts: list[str] = []
    sleeps: list[float] = []

    def poster(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        attempts.append(payload["event_id"])
        if len(attempts) < 3:
            raise RuntimeError("temporary failure")
        return {"accepted": True}

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    client = OrderApiClient(
        "http://api.test",
        poster=poster,
    )
    plan = create_order_plan(
        store_id="store-001",
        run_id="retry-test",
        sequence=1,
        menus=_menus("store-001"),
        rng=random.Random(1),
    )
    event = materialize_order_events(
        plan,
        datetime(2026, 7, 30, 10, 0, tzinfo=ZoneInfo("Asia/Seoul")),
    )[0]

    asyncio.run(
        send_event_with_retry(
            client,
            event,
            max_attempts=3,
            sleep=fake_sleep,
        )
    )

    assert attempts == [event.event_id, event.event_id, event.event_id]
    assert sleeps == [1, 2]


def test_api_readiness_checks_database_schema() -> None:
    requested_urls: list[str] = []

    def getter(url: str, timeout: float) -> dict[str, Any]:
        requested_urls.append(url)
        if url.endswith("/health"):
            return {"database": "ok"}
        raise RuntimeError("relation order_events does not exist")

    client = OrderApiClient("http://api.test", getter=getter)

    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        client.check_ready()

    assert requested_urls == [
        "http://api.test/health",
        "http://api.test/api/stores/summary",
    ]


def test_generated_events_are_accepted_and_duplicate_event_is_idempotent(
    client,
) -> None:
    plan = create_order_plan(
        store_id="store-001",
        run_id="api-test",
        sequence=1,
        menus=_menus("store-001"),
        rng=random.Random(2),
    )
    event = materialize_order_events(
        plan,
        datetime(2026, 7, 30, 10, 0, tzinfo=KST),
    )[0]
    payload = event.model_dump(mode="json")

    first = client.post("/internal/order-events", json=payload)
    duplicate = client.post("/internal/order-events", json=payload)
    latest = client.get(
        f"/api/stores/{event.store_id}/orders/{event.order_id}"
    )

    assert first.status_code == 202
    assert duplicate.status_code == 202
    assert latest.status_code == 200
    assert latest.json()["event_id"] == event.event_id
    assert latest.json()["status"] == "received"
