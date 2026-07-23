"""두 매장 데모 시나리오를 실행 중인 공통 API에 적재한다."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
import sys
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

from pydantic import ValidationError

from .config import get_settings
from .models import OrderEvent, StoreState


JsonObject = dict[str, Any]
PostJson = Callable[[str, JsonObject, float], JsonObject]


@dataclass
class FranchiseScenario:
    scenario_id: str
    store_ids: list[str]
    states: list[JsonObject]
    orders: list[JsonObject]
    start_at: datetime
    end_at: datetime


@dataclass
class LoadReport:
    state_success_count: int = 0
    order_success_count: int = 0
    errors: list[str] = field(default_factory=list)


def load_scenario_file(path: Path) -> FranchiseScenario:
    """파일 전체를 검증한 뒤 API에 바로 보낼 수 있는 값으로 변환한다."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"시나리오 파일이 없습니다: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"시나리오 JSON 형식이 잘못됐습니다: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("시나리오 최상위 값은 JSON 객체여야 합니다.")

    stores = data.get("stores")
    states = data.get("states")
    orders = data.get("orders")
    if not isinstance(stores, list) or not stores:
        raise ValueError("stores 목록이 없거나 비어 있습니다.")
    if not isinstance(states, list) or not states:
        raise ValueError("states 목록이 없거나 비어 있습니다.")
    if not isinstance(orders, list) or not orders:
        raise ValueError("orders 목록이 없거나 비어 있습니다.")

    store_ids = [
        store.get("store_id")
        for store in stores
        if isinstance(store, dict) and isinstance(store.get("store_id"), str)
    ]
    if len(store_ids) != len(stores) or len(set(store_ids)) != len(store_ids):
        raise ValueError("stores의 store_id가 없거나 중복됐습니다.")

    validated_states: list[StoreState] = []
    for index, item in enumerate(states):
        try:
            validated = StoreState.model_validate(item)
        except ValidationError as exc:
            raise ValueError(f"states[{index}] 형식이 잘못됐습니다: {exc}") from exc
        if validated.store_id not in store_ids:
            raise ValueError(
                f"states[{index}]의 매장 {validated.store_id}가 stores에 없습니다."
            )
        validated_states.append(validated)

    validated_orders: list[OrderEvent] = []
    for index, item in enumerate(orders):
        try:
            validated = OrderEvent.model_validate(item)
        except ValidationError as exc:
            raise ValueError(f"orders[{index}] 형식이 잘못됐습니다: {exc}") from exc
        if validated.store_id not in store_ids:
            raise ValueError(
                f"orders[{index}]의 매장 {validated.store_id}가 stores에 없습니다."
            )
        validated_orders.append(validated)

    observed_times = [state.captured_at for state in validated_states] + [
        order.occurred_at for order in validated_orders
    ]
    return FranchiseScenario(
        scenario_id=str(data.get("scenario_id") or path.stem),
        store_ids=store_ids,
        states=[state.model_dump(mode="json") for state in validated_states],
        orders=[order.model_dump(mode="json") for order in validated_orders],
        start_at=min(observed_times),
        end_at=max(observed_times),
    )


def post_json(url: str, payload: JsonObject, timeout: float) -> JsonObject:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return _request_json(request, timeout)


def get_json(url: str, timeout: float) -> JsonObject:
    return _request_json(urllib.request.Request(url, method="GET"), timeout)


def _request_json(
    request: urllib.request.Request,
    timeout: float,
) -> JsonObject:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {error_body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"API 연결 실패: {exc.reason}") from exc

    if not raw_body:
        return {}
    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("API 응답이 올바른 JSON이 아닙니다.") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("API 응답이 JSON 객체가 아닙니다.")
    return parsed


def send_scenario(
    scenario: FranchiseScenario,
    api_base_url: str,
    timeout: float = 5.0,
    sender: PostJson = post_json,
) -> LoadReport:
    """검증을 마친 상태와 주문을 각각 기존 내부 API로 전송한다."""
    report = LoadReport()
    api_base_url = api_base_url.rstrip("/")

    for index, state in enumerate(scenario.states):
        try:
            sender(
                f"{api_base_url}/internal/store-states",
                state,
                timeout,
            )
        except RuntimeError as exc:
            report.errors.append(f"states[{index}] 전송 실패: {exc}")
        else:
            report.state_success_count += 1

    for index, order in enumerate(scenario.orders):
        try:
            sender(
                f"{api_base_url}/internal/order-events",
                order,
                timeout,
            )
        except RuntimeError as exc:
            report.errors.append(f"orders[{index}] 전송 실패: {exc}")
        else:
            report.order_success_count += 1

    return report


def get_scenario_summary(
    scenario: FranchiseScenario,
    api_base_url: str,
    timeout: float,
) -> JsonObject:
    query = urllib.parse.urlencode(
        {
            "start_at": scenario.start_at.isoformat(),
            "end_at": scenario.end_at.isoformat(),
        }
    )
    return get_json(
        f"{api_base_url.rstrip('/')}/api/stores/summary?{query}",
        timeout,
    )


def _build_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="두 매장 데모 시나리오를 PostgreSQL API에 적재합니다."
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=settings.sample_data_dir / "franchise_scenario.json",
        help="시나리오 JSON 경로",
    )
    parser.add_argument(
        "--api",
        default=os.getenv("SCENARIO_API_BASE_URL", "http://localhost:8000"),
        help="공통 API 기본 주소",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="API 요청 제한 시간(초)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        health = get_json(f"{args.api.rstrip('/')}/health", args.timeout)
        if health.get("database") != "ok":
            raise RuntimeError(
                f"PostgreSQL 연결 상태가 정상이 아닙니다: {health.get('database')}"
            )
        scenario = load_scenario_file(args.file)
        report = send_scenario(scenario, args.api, args.timeout)
    except (RuntimeError, ValueError) as exc:
        print(f"적재 중단: {exc}", file=sys.stderr)
        return 1

    print(
        f"{scenario.scenario_id} 전송 완료: "
        f"상태 {report.state_success_count}/{len(scenario.states)}건, "
        f"주문 {report.order_success_count}/{len(scenario.orders)}건"
    )
    if report.errors:
        for error in report.errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    try:
        summary = get_scenario_summary(scenario, args.api, args.timeout)
    except RuntimeError as exc:
        print(f"집계 확인 실패: {exc}", file=sys.stderr)
        return 1

    summaries = {
        store.get("store_id"): store
        for store in summary.get("stores", [])
        if isinstance(store, dict)
    }
    missing_store_ids = [
        store_id for store_id in scenario.store_ids if store_id not in summaries
    ]
    if missing_store_ids:
        print(
            f"집계에서 매장을 찾지 못했습니다: {', '.join(missing_store_ids)}",
            file=sys.stderr,
        )
        return 1

    for store_id in scenario.store_ids:
        traffic = summaries[store_id].get("traffic_summary") or {}
        print(
            f"- {store_id}: 최대 인원 "
            f"{traffic.get('peak_visible_person_count')}명, 최대 대기 "
            f"{traffic.get('peak_queue_count_estimate')}명"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
