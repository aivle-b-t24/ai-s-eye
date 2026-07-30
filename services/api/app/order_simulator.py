"""기존 주문 API를 이용해 합성 데모 주문을 자동 생성한다.

``live`` 모드는 주문 상태를 실제 시간에 맞춰 순차적으로 전송하고,
``seed`` 모드는 본사 기간 분석에 사용할 과거 주문 이력을 빠르게 적재한다.
DB에 직접 접근하지 않으며 실제 POS/KDS와 같은 ``/internal/order-events`` API를
사용한다.

이 모듈은 주문 이벤트 생성기다. 직원 수, 제조 자원, 대기열, 좌석, 이탈을
계산하는 What-if 운영 시뮬레이터는 아니다. 생성 주문은 ``sim-`` 접두사로
구분하지만 현재 본사 집계에는 실제 주문과 함께 포함되므로 데모 DB에서만 쓴다.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import logging
import os
import random
import re
import signal
import sys
from typing import Any
from zoneinfo import ZoneInfo

from .models import OrderEvent, OrderItem, OrderStatus
from .scenario_loader import get_json, post_json


KST = ZoneInfo("Asia/Seoul")
LOGGER = logging.getLogger("order-simulator")
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,40}$")
LIVE_INTERVALS_MINUTES = {
    "normal": (3.0, 6.0),
    "lunch_peak": (0.5, 1.5),
}
STORE_INTERVAL_MULTIPLIERS = {
    "store-001": 1.0,
    "store-002": 1.35,
}
SEED_HOURLY_RATES = {
    "store-001": {
        "opening": 3.0,
        "lunch": 8.0,
        "afternoon": 6.0,
        "evening": 5.0,
    },
    "store-002": {
        "opening": 2.0,
        "lunch": 4.0,
        "afternoon": 5.0,
        "evening": 3.0,
    },
}
DEFAULT_SEED_HOURLY_RATES = {
    "opening": 2.0,
    "lunch": 5.0,
    "afternoon": 4.0,
    "evening": 3.0,
}

JsonObject = dict[str, Any]
GetJson = Callable[[str, float], JsonObject]
PostJson = Callable[[str, JsonObject, float], JsonObject]
AsyncSleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class MenuOption:
    menu_id: str
    name: str | None
    prep_minutes: float


@dataclass(frozen=True)
class PlannedOrder:
    order_id: str
    store_id: str
    items: tuple[OrderItem, ...]
    transitions: tuple[tuple[OrderStatus, float], ...]


class OrderApiClient:
    """주문 시뮬레이터가 사용하는 최소 API 클라이언트."""

    def __init__(
        self,
        api_base_url: str,
        *,
        timeout: float = 5.0,
        getter: GetJson = get_json,
        poster: PostJson = post_json,
    ) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self.timeout = timeout
        self._getter = getter
        self._poster = poster

    def check_ready(self) -> None:
        health = self._getter(f"{self.api_base_url}/health", self.timeout)
        if health.get("database") != "ok":
            raise RuntimeError(
                "PostgreSQL 연결 상태가 정상이 아닙니다: "
                f"{health.get('database', 'unknown')}"
            )
        try:
            self._getter(f"{self.api_base_url}/api/stores/summary", self.timeout)
        except RuntimeError as exc:
            raise RuntimeError(
                "API 테이블을 조회할 수 없습니다. "
                "docker compose exec api alembic upgrade head를 먼저 실행해 주세요."
            ) from exc

    def get_available_menus(self, store_id: str) -> list[MenuOption]:
        payload = self._getter(
            f"{self.api_base_url}/api/stores/{store_id}/menus",
            self.timeout,
        )
        return parse_available_menus(payload, store_id)

    def send_order_event(self, event: OrderEvent) -> JsonObject:
        return self._poster(
            f"{self.api_base_url}/internal/order-events",
            event.model_dump(mode="json"),
            self.timeout,
        )


def parse_available_menus(payload: JsonObject, store_id: str) -> list[MenuOption]:
    """메뉴 API 응답에서 해당 매장의 판매 가능 메뉴만 추린다."""
    raw_menus = payload.get("menus")
    if not isinstance(raw_menus, list):
        raise ValueError(f"{store_id} 메뉴 응답에 menus 목록이 없습니다.")

    menus: list[MenuOption] = []
    for row in raw_menus:
        if not isinstance(row, dict):
            continue
        if row.get("store_id") != store_id or row.get("available") is not True:
            continue
        menu_id = row.get("menu_id")
        prep_minutes = row.get("prep_minutes")
        if not isinstance(menu_id, str) or not menu_id:
            continue
        if not isinstance(prep_minutes, (int, float)) or prep_minutes <= 0:
            continue
        name = row.get("name")
        menus.append(
            MenuOption(
                menu_id=menu_id,
                name=name if isinstance(name, str) else None,
                prep_minutes=float(prep_minutes),
            )
        )

    if not menus:
        raise ValueError(f"{store_id}에 주문 가능한 메뉴가 없습니다.")
    return menus


def validate_run_id(run_id: str) -> str:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError(
            "run_id는 영문, 숫자, 점, 밑줄, 하이픈만 사용해 40자 이내로 입력해야 합니다."
        )
    return run_id


def create_order_plan(
    *,
    store_id: str,
    run_id: str,
    sequence: int,
    menus: list[MenuOption],
    rng: random.Random,
) -> PlannedOrder:
    """메뉴와 제조시간을 포함한 주문 한 건의 상태 전환 계획을 만든다."""
    if sequence < 1:
        raise ValueError("sequence는 1 이상이어야 합니다.")
    if not menus:
        raise ValueError("주문을 만들 메뉴가 없습니다.")

    item_type_count = rng.randint(1, min(2, len(menus)))
    selected = rng.sample(menus, item_type_count)
    quantities = [rng.randint(1, 2) for _ in selected]
    items = tuple(
        OrderItem(menu_id=menu.menu_id, name=menu.name, quantity=quantity)
        for menu, quantity in zip(selected, quantities, strict=True)
    )

    total_quantity = sum(quantities)
    prep_seconds = (
        max(menu.prep_minutes for menu in selected) * 60
        + max(total_quantity - 1, 0) * 30
    )
    ready_offset = max(15.0, prep_seconds)
    order_id = f"sim-{run_id}-{store_id}-{sequence:06d}"
    if len(order_id) > 90:
        raise ValueError("생성된 order_id가 너무 깁니다. run_id를 줄여주세요.")

    return PlannedOrder(
        order_id=order_id,
        store_id=store_id,
        items=items,
        transitions=(
            (OrderStatus.RECEIVED, 0.0),
            (OrderStatus.PREPARING, 15.0),
            (OrderStatus.READY, ready_offset),
            (OrderStatus.COMPLETED, ready_offset + 60.0),
        ),
    )


def create_order_event(
    plan: PlannedOrder,
    status: OrderStatus,
    occurred_at: datetime,
) -> OrderEvent:
    if occurred_at.tzinfo is None:
        raise ValueError("occurred_at에는 시간대가 포함돼야 합니다.")
    if status not in {transition for transition, _ in plan.transitions}:
        raise ValueError(f"주문 계획에 없는 상태입니다: {status}")
    return OrderEvent(
        event_id=f"{plan.order_id}-{status.value}",
        order_id=plan.order_id,
        store_id=plan.store_id,
        occurred_at=occurred_at,
        status=status,
        items=list(plan.items),
    )


def materialize_order_events(
    plan: PlannedOrder,
    received_at: datetime,
) -> list[OrderEvent]:
    """가상 시각을 보존해야 하는 seed 모드용 이벤트 목록을 만든다."""
    return [
        create_order_event(
            plan,
            status,
            received_at + timedelta(seconds=offset_seconds),
        )
        for status, offset_seconds in plan.transitions
    ]


async def send_event_with_retry(
    client: OrderApiClient,
    event: OrderEvent,
    *,
    max_attempts: int = 6,
    sleep: AsyncSleep = asyncio.sleep,
) -> None:
    """동일한 event_id로 지수 백오프 재시도한다."""
    if max_attempts < 1:
        raise ValueError("max_attempts는 1 이상이어야 합니다.")

    for attempt in range(1, max_attempts + 1):
        try:
            await asyncio.to_thread(client.send_order_event, event)
            return
        except RuntimeError:
            if attempt >= max_attempts:
                raise
            delay = min(2 ** (attempt - 1), 30)
            LOGGER.warning(
                "주문 이벤트 전송 실패, %.0f초 후 재시도 (%s/%s): %s",
                delay,
                attempt,
                max_attempts,
                event.event_id,
            )
            await sleep(delay)


def _real_seconds(virtual_seconds: float, speed: float) -> float:
    if speed <= 0:
        raise ValueError("speed는 0보다 커야 합니다.")
    return virtual_seconds / speed


async def _wait_or_stopped(stop_event: asyncio.Event, seconds: float) -> bool:
    if seconds <= 0:
        return stop_event.is_set()
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except TimeoutError:
        return False
    return True


class LiveOrderSimulator:
    def __init__(
        self,
        *,
        client: OrderApiClient,
        menus_by_store: dict[str, list[MenuOption]],
        run_id: str,
        scenario: str,
        speed: float,
        seed: int,
        max_attempts: int,
        stop_grace_seconds: float,
    ) -> None:
        if scenario not in LIVE_INTERVALS_MINUTES:
            raise ValueError(f"지원하지 않는 시나리오입니다: {scenario}")
        if speed <= 0:
            raise ValueError("speed는 0보다 커야 합니다.")
        if max_attempts < 1:
            raise ValueError("max_attempts는 1 이상이어야 합니다.")
        if stop_grace_seconds < 0:
            raise ValueError("stop_grace_seconds는 0 이상이어야 합니다.")
        self.client = client
        self.menus_by_store = menus_by_store
        self.run_id = validate_run_id(run_id)
        self.scenario = scenario
        self.speed = speed
        self.seed = seed
        self.max_attempts = max_attempts
        self.stop_grace_seconds = stop_grace_seconds
        self.stop_event = asyncio.Event()
        self.active_orders: set[asyncio.Task[None]] = set()

    async def run(self) -> None:
        producers = [
            asyncio.create_task(
                self._produce_store(store_id, store_index),
                name=f"order-producer-{store_id}",
            )
            for store_index, store_id in enumerate(self.menus_by_store)
        ]
        LOGGER.info(
            "LIVE 주문 시뮬레이션 시작: run=%s, stores=%s, scenario=%s, speed=%.1fx",
            self.run_id,
            ",".join(self.menus_by_store),
            self.scenario,
            self.speed,
        )

        await self.stop_event.wait()
        await asyncio.gather(*producers, return_exceptions=True)
        await self._drain_active_orders()

    def stop(self) -> None:
        self.stop_event.set()

    async def _produce_store(self, store_id: str, store_index: int) -> None:
        store_seed = self.seed + _stable_store_seed(store_id)
        schedule_rng = random.Random(store_seed)
        menu_rng = random.Random(store_seed + 1_000_003)
        sequence = 1
        if await _wait_or_stopped(self.stop_event, store_index * 1.5):
            return

        while not self.stop_event.is_set():
            plan = create_order_plan(
                store_id=store_id,
                run_id=self.run_id,
                sequence=sequence,
                menus=self.menus_by_store[store_id],
                rng=menu_rng,
            )
            task = asyncio.create_task(
                self._run_order(plan),
                name=f"order-{plan.order_id}",
            )
            self.active_orders.add(task)
            task.add_done_callback(self.active_orders.discard)
            sequence += 1

            minimum, maximum = LIVE_INTERVALS_MINUTES[self.scenario]
            multiplier = STORE_INTERVAL_MULTIPLIERS.get(store_id, 1.15)
            virtual_seconds = (
                schedule_rng.uniform(minimum, maximum) * 60 * multiplier
            )
            if await _wait_or_stopped(
                self.stop_event,
                _real_seconds(virtual_seconds, self.speed),
            ):
                return

    async def _run_order(self, plan: PlannedOrder) -> None:
        previous_offset = 0.0
        for status, offset_seconds in plan.transitions:
            delay = _real_seconds(offset_seconds - previous_offset, self.speed)
            if delay:
                await asyncio.sleep(delay)
            event = create_order_event(plan, status, datetime.now(KST))
            try:
                await send_event_with_retry(
                    self.client,
                    event,
                    max_attempts=self.max_attempts,
                )
            except RuntimeError as exc:
                LOGGER.error("주문 %s 전송 중단: %s", plan.order_id, exc)
                return
            LOGGER.info(
                "%s %s (%s)",
                plan.store_id,
                plan.order_id,
                status.value,
            )
            previous_offset = offset_seconds

    async def _drain_active_orders(self) -> None:
        active = list(self.active_orders)
        if not active:
            return
        LOGGER.info("진행 중인 주문 %s건을 마무리합니다.", len(active))
        done, pending = await asyncio.wait(
            active,
            timeout=self.stop_grace_seconds,
        )
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
            LOGGER.warning(
                "종료 제한시간을 넘긴 주문 %s건은 다음 상태 전송을 중단했습니다.",
                len(pending),
            )
        for task in done:
            if not task.cancelled() and task.exception() is not None:
                LOGGER.error("주문 작업 오류: %s", task.exception())


def _stable_store_seed(store_id: str) -> int:
    return sum((index + 1) * ord(char) for index, char in enumerate(store_id))


def _hourly_rate(store_id: str, hour: int) -> float:
    rates = SEED_HOURLY_RATES.get(store_id, DEFAULT_SEED_HOURLY_RATES)
    if 9 <= hour < 11:
        return rates["opening"]
    if 11 <= hour < 14:
        return rates["lunch"]
    if 14 <= hour < 18:
        return rates["afternoon"]
    return rates["evening"]


def _seed_received_times(
    *,
    store_id: str,
    start_date: date,
    end_date: date,
    rng: random.Random,
) -> Iterable[datetime]:
    current_date = start_date
    while current_date <= end_date:
        for hour in range(9, 22):
            rate = _hourly_rate(store_id, hour)
            cursor = datetime.combine(current_date, time(hour=hour), tzinfo=KST)
            hour_end = cursor + timedelta(hours=1)
            while True:
                cursor += timedelta(seconds=rng.expovariate(rate / 3600))
                if cursor >= hour_end:
                    break
                yield cursor
        current_date += timedelta(days=1)


def generate_seed_events(
    *,
    menus_by_store: dict[str, list[MenuOption]],
    run_id: str,
    days: int,
    end_date: date,
    seed: int,
) -> list[OrderEvent]:
    """동일한 입력에서 동일한 과거 주문 이벤트를 생성한다."""
    if days < 1 or days > 31:
        raise ValueError("days는 1~31 범위여야 합니다.")
    validate_run_id(run_id)
    start_date = end_date - timedelta(days=days - 1)
    events: list[OrderEvent] = []

    for store_id, menus in menus_by_store.items():
        store_seed = seed + _stable_store_seed(store_id)
        arrival_rng = random.Random(store_seed)
        menu_rng = random.Random(store_seed + 1_000_003)
        for sequence, received_at in enumerate(
            _seed_received_times(
                store_id=store_id,
                start_date=start_date,
                end_date=end_date,
                rng=arrival_rng,
            ),
            start=1,
        ):
            plan = create_order_plan(
                store_id=store_id,
                run_id=run_id,
                sequence=sequence,
                menus=menus,
                rng=menu_rng,
            )
            events.extend(materialize_order_events(plan, received_at))

    return sorted(events, key=lambda event: (event.occurred_at, event.event_id))


async def send_seed_events(
    client: OrderApiClient,
    events: list[OrderEvent],
    *,
    max_attempts: int,
) -> None:
    total = len(events)
    for index, event in enumerate(events, start=1):
        await send_event_with_retry(
            client,
            event,
            max_attempts=max_attempts,
        )
        if index % 100 == 0 or index == total:
            LOGGER.info("과거 주문 적재 %s/%s건", index, total)


def _split_store_ids(raw_store_ids: str) -> list[str]:
    store_ids = [
        store_id.strip()
        for store_id in raw_store_ids.split(",")
        if store_id.strip()
    ]
    if not store_ids:
        raise ValueError("최소 한 개의 매장 ID가 필요합니다.")
    if len(set(store_ids)) != len(store_ids):
        raise ValueError("매장 ID가 중복됐습니다.")
    return store_ids


def _default_live_run_id() -> str:
    return datetime.now(KST).strftime("live-%Y%m%d-%H%M%S")


def _default_seed_run_id(end_date: date, days: int, seed: int) -> str:
    return f"seed-{end_date:%Y%m%d}-{days}d-s{seed}"


def _common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--api",
        default=os.getenv("ORDER_SIM_API_BASE_URL", "http://localhost:8000"),
        help="공통 API 기본 주소",
    )
    parser.add_argument(
        "--stores",
        default=os.getenv("ORDER_SIM_STORE_IDS", "store-001,store-002"),
        help="쉼표로 구분한 매장 ID",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.getenv("ORDER_SIM_REQUEST_TIMEOUT_SECONDS", "5")),
        help="API 요청 제한 시간(초)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=int(os.getenv("ORDER_SIM_SEED", "20260730")),
        help="재현 가능한 난수 seed",
    )
    parser.add_argument(
        "--run-id",
        default=os.getenv("ORDER_SIM_RUN_ID") or None,
        help="주문 ID에 포함할 실행 식별자",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=int(os.getenv("ORDER_SIM_MAX_ATTEMPTS", "6")),
        help="이벤트별 최대 API 전송 횟수",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="기존 주문 API를 이용해 실시간 또는 과거 주문을 생성합니다."
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    live = subparsers.add_parser("live", help="주문 상태를 실시간으로 재생")
    _common_arguments(live)
    live.add_argument(
        "--scenario",
        choices=sorted(LIVE_INTERVALS_MINUTES),
        default=os.getenv("ORDER_SIM_SCENARIO", "normal"),
    )
    live.add_argument(
        "--speed",
        type=float,
        default=float(os.getenv("ORDER_SIM_SPEED", "12")),
        help="가상시간 재생 배속",
    )
    live.add_argument(
        "--stop-grace-seconds",
        type=float,
        default=float(os.getenv("ORDER_SIM_STOP_GRACE_SECONDS", "30")),
        help="종료 시 진행 중 주문을 기다릴 최대 시간",
    )

    seed_parser = subparsers.add_parser(
        "seed",
        help="본사 기간 분석용 과거 주문을 적재",
    )
    _common_arguments(seed_parser)
    seed_parser.add_argument(
        "--days",
        type=int,
        default=int(os.getenv("ORDER_SIM_DAYS", "7")),
    )
    seed_parser.add_argument(
        "--end-date",
        type=date.fromisoformat,
        default=None,
        help="마지막 생성 날짜(YYYY-MM-DD), 기본값은 한국시간 기준 어제",
    )
    seed_parser.add_argument(
        "--apply",
        action="store_true",
        help="생성 결과를 API에 실제 적재. 생략하면 건수만 확인",
    )
    return parser


def _arguments_with_default_mode(argv: list[str] | None) -> list[str]:
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] in {"live", "seed"}:
        return raw
    return [os.getenv("ORDER_SIM_MODE", "live"), *raw]


def _load_menus(
    client: OrderApiClient,
    store_ids: list[str],
) -> dict[str, list[MenuOption]]:
    return {
        store_id: client.get_available_menus(store_id)
        for store_id in store_ids
    }


async def _run_live_command(
    args: argparse.Namespace,
    client: OrderApiClient,
    menus_by_store: dict[str, list[MenuOption]],
) -> None:
    run_id = validate_run_id(args.run_id or _default_live_run_id())
    LOGGER.warning(
        "합성 LIVE 주문이 본사 주문 집계에 포함됩니다. 데모 DB에서만 실행하세요."
    )
    simulator = LiveOrderSimulator(
        client=client,
        menus_by_store=menus_by_store,
        run_id=run_id,
        scenario=args.scenario,
        speed=args.speed,
        seed=args.seed,
        max_attempts=args.max_attempts,
        stop_grace_seconds=args.stop_grace_seconds,
    )
    loop = asyncio.get_running_loop()
    for signal_number in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_number, simulator.stop)
        except NotImplementedError:
            pass
    await simulator.run()


async def _run_seed_command(
    args: argparse.Namespace,
    client: OrderApiClient,
    menus_by_store: dict[str, list[MenuOption]],
) -> None:
    if args.max_attempts < 1:
        raise ValueError("max_attempts는 1 이상이어야 합니다.")
    end_date = args.end_date or (datetime.now(KST).date() - timedelta(days=1))
    run_id = validate_run_id(
        args.run_id or _default_seed_run_id(end_date, args.days, args.seed)
    )
    events = generate_seed_events(
        menus_by_store=menus_by_store,
        run_id=run_id,
        days=args.days,
        end_date=end_date,
        seed=args.seed,
    )
    order_count = len({event.order_id for event in events})
    LOGGER.info(
        "과거 주문 생성 완료: run=%s, orders=%s, events=%s, period=%s~%s",
        run_id,
        order_count,
        len(events),
        end_date - timedelta(days=args.days - 1),
        end_date,
    )
    if not args.apply:
        LOGGER.info(
            "미리보기만 완료했습니다. API에는 전송하지 않았습니다. "
            "적재하려면 seed 명령에 --apply를 추가하세요."
        )
        return
    LOGGER.warning(
        "합성 과거 주문이 본사 주문 집계에 포함됩니다. 데모 DB에서만 적재하세요."
    )
    await send_seed_events(
        client,
        events,
        max_attempts=args.max_attempts,
    )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=os.getenv("ORDER_SIM_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    parser = _build_parser()
    try:
        args = parser.parse_args(_arguments_with_default_mode(argv))
        if args.timeout <= 0:
            raise ValueError("timeout은 0보다 커야 합니다.")
        store_ids = _split_store_ids(args.stores)
        client = OrderApiClient(args.api, timeout=args.timeout)
        client.check_ready()
        menus_by_store = _load_menus(client, store_ids)
        if args.mode == "live":
            asyncio.run(_run_live_command(args, client, menus_by_store))
        else:
            asyncio.run(_run_seed_command(args, client, menus_by_store))
    except (RuntimeError, ValueError) as exc:
        LOGGER.error("주문 시뮬레이터 중단: %s", exc)
        return 1
    except KeyboardInterrupt:
        LOGGER.info("사용자 요청으로 주문 시뮬레이터를 종료합니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
