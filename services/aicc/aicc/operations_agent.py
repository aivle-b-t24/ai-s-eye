"""본사 운영 의사결정용 제한형 Tool-calling Agent."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import logging
from typing import Any, Iterator
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from .client import StoreApiClient
from .config import get_settings
from .franchise_insights import build_client


logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))
MAX_AGENT_TURNS = 5
FALLBACK_PROFILE = [19.2, 30.0, 24.0]


class OperationsAgentRequest(BaseModel):
    store_id: str = Field(min_length=1)
    start_at: datetime
    end_at: datetime
    duration_minutes: int = Field(default=180, ge=30, le=480)
    event_multiplier: float = Field(default=1.6, ge=1, le=4)
    current_staff_count: int = Field(default=1, ge=1, le=10)
    max_staff_count: int = Field(default=4, ge=1, le=10)
    average_service_minutes: float = Field(default=4, ge=0.5, le=20)
    patience_minutes: float = Field(default=8, ge=1, le=60)
    seat_count: int = Field(default=16, ge=0, le=100)
    dine_in_rate: float = Field(default=0.65, ge=0, le=1)
    seed: int = Field(default=20260730, ge=0, le=2_147_483_647)

    @model_validator(mode="after")
    def validate_period(self) -> "OperationsAgentRequest":
        if self.start_at.tzinfo is None or self.end_at.tzinfo is None:
            raise ValueError("start_at and end_at must include a timezone")
        if self.start_at >= self.end_at:
            raise ValueError("start_at must be earlier than end_at")
        if self.end_at - self.start_at > timedelta(days=31):
            raise ValueError("analysis period must not exceed 31 days")
        if self.current_staff_count > self.max_staff_count:
            raise ValueError("current_staff_count must not exceed max_staff_count")
        return self


SYSTEM_PROMPT = """너는 프랜차이즈 본사의 제한형 운영 의사결정 Agent다.

목표는 선택 매장의 행사 시간대에 현재 인원부터 투입 가능 최대 인원까지 공정하게
탐색하고, 운영 목표를 만족하는 최소 인원을 찾는 것이다.
반드시 도구로 실제 데이터를 확인하고, 다음 순서에 필요한 도구를 스스로 선택한다.
- 매장 집계와 시간대별 추이를 모두 확인한다.
- 그 다음 동일 수요 직원 비교를 실행한다.
- 도구 결과에 없는 숫자는 만들지 않는다.
- 실제 인력 배치를 변경하지 않고 슈퍼바이저 검토안만 제시한다.
- 완료되면 JSON만 반환한다: {"summary":"짧은 판단", "caveat":"한계"}
"""


def _iso(value: datetime) -> str:
    return value.isoformat()


def _compact_store_summary(summary: dict[str, Any], store_id: str) -> dict[str, Any]:
    store = next(
        (item for item in summary.get("stores", []) if item.get("store_id") == store_id),
        None,
    )
    if store is None:
        return {"ok": False, "message": "선택 매장의 집계 데이터가 없습니다."}
    traffic = store.get("traffic_summary") or {}
    orders = store.get("order_summary") or {}
    return {
        "ok": True,
        "store_id": store_id,
        "average_people": traffic.get("average_visible_person_count"),
        "peak_people": traffic.get("peak_visible_person_count"),
        "peak_queue": traffic.get("peak_queue_count_estimate"),
        "total_orders": orders.get("total_order_count", 0),
        "data_sources": orders.get("data_sources") or [],
    }


def build_peak_arrival_profile(
    timeline: dict[str, Any],
    duration_minutes: int,
) -> dict[str, Any]:
    """KST 시간대별 평균 주문량에서 가장 강한 연속 3시간을 찾는다."""
    hourly: dict[int, list[float]] = defaultdict(list)
    for point in timeline.get("points", []):
        try:
            captured = datetime.fromisoformat(
                str(point["start_at"]).replace("Z", "+00:00")
            ).astimezone(KST)
            hourly[captured.hour].append(float(point.get("order_count", 0)))
        except (KeyError, TypeError, ValueError):
            continue

    averages = {
        hour: sum(values) / len(values)
        for hour, values in hourly.items()
        if values
    }
    candidates: list[tuple[float, int, list[float]]] = []
    for start_hour in range(22):
        rates = [averages.get(hour, 0) for hour in range(start_hour, start_hour + 3)]
        candidates.append((sum(rates), start_hour, rates))
    _, start_hour, rates = max(candidates, key=lambda item: (item[0], -item[1]))

    source = "selected_period_hourly_orders"
    if sum(rates) <= 0 or len(timeline.get("points", [])) < 3:
        rates = FALLBACK_PROFILE
        start_hour = 11
        source = "presentation_fallback"

    boundaries = [0, duration_minutes / 3, duration_minutes * 2 / 3, duration_minutes]
    segments = [
        {
            "start_minute": boundaries[index],
            "end_minute": boundaries[index + 1],
            "arrivals_per_hour": round(rate, 2),
        }
        for index, rate in enumerate(rates)
    ]
    return {
        "source": source,
        "window_label": f"{start_hour:02d}:00~{start_hour + 3:02d}:00 KST",
        "rates": [round(rate, 2) for rate in rates],
        "segments": segments,
    }


def _verified_recommendation(comparison: dict[str, Any]) -> dict[str, Any]:
    options = comparison.get("staffing_options") or []
    if options:
        passing = [option for option in options if option.get("meets_targets")]
        selected_option = min(
            passing or options,
            key=lambda option: option["staff_count"]
            if passing
            else -option["staff_count"],
        )
        selected = selected_option["staff_count"]
        capacity_sufficient = bool(passing)
        current_staff_count = comparison.get("current_staff_count", 1)
        current_option = next(
            (
                option
                for option in options
                if option["staff_count"] == current_staff_count
            ),
            options[0],
        )
        current = current_option["metrics"]
        recommended = selected_option["metrics"]
    else:
        # 구버전 비교 API와의 배포 순서 호환 경로다.
        current = comparison["event_one"]["metrics"]
        recommended = comparison["event_two"]["metrics"]
        current_staff_count = 1
        wait_gain = current["average_wait_minutes"] - recommended["average_wait_minutes"]
        abandon_gain = current["abandoned_orders"] - recommended["abandoned_orders"]
        selected = 2 if wait_gain > 0 or abandon_gain > 0 else 1
        capacity_sufficient = True
        if selected == 1:
            recommended = current

    wait_reduction = round(
        current["average_wait_minutes"] - recommended["average_wait_minutes"],
        2,
    )
    wait_reduction_percent = (
        round(wait_reduction / current["average_wait_minutes"] * 100, 1)
        if current["average_wait_minutes"] > 0
        else 0
    )
    completed_gain = recommended["completed_orders"] - current["completed_orders"]
    abandoned_reduction = (
        current["abandoned_orders"] - recommended["abandoned_orders"]
    )
    max_staff_count = comparison.get("max_staff_count", selected)
    if not capacity_sufficient:
        summary = (
            f"투입 가능한 최대 직원 {max_staff_count}명으로도 설정한 운영 목표를 모두 "
            "충족하지 못했습니다. 최대 인력 투입과 함께 주문 제한·제조 단순화 등 "
            "추가 운영 대책을 검토하세요."
        )
    elif selected > current_staff_count:
        summary = (
            f"행사 시간대 직원 {selected}명을 검토하세요. 현재 "
            f"{current_staff_count}명 대비 평균 대기가 "
            f"{wait_reduction:.1f}분 줄고 완료 주문은 {completed_gain}건, "
            f"주문 포기는 {abandoned_reduction}건 개선됩니다."
        )
    elif selected < current_staff_count:
        summary = (
            f"운영 목표를 만족하는 최소 인원은 {selected}명입니다. 현재 "
            f"{current_staff_count}명에서 조정하더라도 평균 대기 "
            f"{recommended['average_wait_minutes']:.1f}분, 주문 포기 "
            f"{recommended['abandoned_orders']}건 수준입니다."
        )
    else:
        summary = (
            f"현재 직원 {current_staff_count}명이 운영 목표를 만족하는 최소 인원입니다. "
            "현재 인원을 유지하고 실제 피크 수요를 함께 확인하세요."
        )
    return {
        "recommended_staff_count": selected,
        "current_staff_count": current_staff_count,
        "max_staff_count": max_staff_count,
        "capacity_sufficient": capacity_sufficient,
        "summary": summary,
        "evidence": {
            "average_wait_reduction_minutes": wait_reduction,
            "average_wait_reduction_percent": wait_reduction_percent,
            "completed_order_gain": completed_gain,
            "abandoned_order_reduction": abandoned_reduction,
            "current_staff_utilization_percent": current["staff_utilization_percent"],
            "recommended_staff_utilization_percent": recommended[
                "staff_utilization_percent"
            ],
        },
        "approval_required": True,
    }


class OperationsDecisionAgent:
    def __init__(
        self,
        store_client: StoreApiClient,
        model_client: Any | None = None,
    ) -> None:
        self._store_client = store_client
        self._model_client = model_client if model_client is not None else build_client()
        self._settings = get_settings()

    def stream(self, request: OperationsAgentRequest) -> Iterator[dict[str, Any]]:
        run_id = f"agent-{uuid4().hex[:12]}"
        sequence = 0
        trace: list[dict[str, Any]] = []
        summary: dict[str, Any] | None = None
        profile: dict[str, Any] | None = None
        comparison: dict[str, Any] | None = None

        def event(event_type: str, title: str, **extra: Any) -> dict[str, Any]:
            nonlocal sequence
            sequence += 1
            item = {
                "event": event_type,
                "run_id": run_id,
                "sequence": sequence,
                "title": title,
                **extra,
            }
            if event_type in {"tool_started", "tool_completed"}:
                trace.append(item.copy())
            return item

        yield event("run_started", "운영 분석을 시작했습니다.", status="running")

        def execute_tool(name: str) -> dict[str, Any]:
            nonlocal summary, profile, comparison
            if name == "get_store_operating_summary":
                raw = self._store_client.get_store_summary(
                    _iso(request.start_at),
                    _iso(request.end_at),
                )
                summary = _compact_store_summary(raw, request.store_id)
                return summary
            if name == "get_hourly_timeline":
                raw = self._store_client.get_store_timeline(
                    request.store_id,
                    _iso(request.start_at),
                    _iso(request.end_at),
                    "1h",
                )
                profile = build_peak_arrival_profile(raw, request.duration_minutes)
                return {
                    "ok": True,
                    "peak_window": profile["window_label"],
                    "hourly_rates": profile["rates"],
                    "demand_source": profile["source"],
                }
            if name == "compare_staffing_options":
                if profile is None:
                    return {
                        "ok": False,
                        "message": "먼저 get_hourly_timeline을 호출해야 합니다.",
                    }
                data_sources = (summary or {}).get("data_sources") or []
                demand_source = (
                    "synthetic_order_simulator"
                    if "synthetic_order_simulator" in data_sources
                    else profile["source"]
                )
                comparison = self._store_client.compare_operations({
                    "store_id": request.store_id,
                    "duration_minutes": request.duration_minutes,
                    "arrival_profile": profile["segments"],
                    "event_multiplier": request.event_multiplier,
                    "current_staff_count": request.current_staff_count,
                    "max_staff_count": request.max_staff_count,
                    "average_service_minutes": request.average_service_minutes,
                    "patience_minutes": request.patience_minutes,
                    "seat_count": request.seat_count,
                    "dine_in_rate": request.dine_in_rate,
                    "seed": request.seed,
                    "demand_source": demand_source,
                    "demand_window_label": profile["window_label"],
                })
                return {
                    "ok": True,
                    "event_demand_trace_id": comparison["event_demand_trace_id"],
                    "current_staff_count": comparison.get("current_staff_count"),
                    "max_staff_count": comparison.get("max_staff_count"),
                    "recommended_staff_count": comparison.get(
                        "recommended_staff_count"
                    ),
                    "capacity_sufficient": comparison.get("capacity_sufficient"),
                    "staffing_options": comparison.get("staffing_options") or [],
                }
            return {"ok": False, "message": f"허용되지 않은 도구입니다: {name}"}

        source = "gemini_tool_agent"
        model_text = ""
        try:
            if self._model_client is None:
                raise RuntimeError("Gemini client is unavailable")
            from google.genai import types

            def get_store_operating_summary() -> dict[str, Any]:
                """선택 기간의 매장별 인원·대기·주문 집계를 조회한다."""
                return {}

            def get_hourly_timeline() -> dict[str, Any]:
                """선택 매장의 1시간 단위 주문 추이와 피크 구간을 조회한다."""
                return {}

            def compare_staffing_options() -> dict[str, Any]:
                """같은 행사 수요로 현재 인원부터 최대 인원까지 비교한다."""
                return {}

            contents: list[Any] = [
                types.Content(
                    role="user",
                    parts=[types.Part(text=(
                        f"{request.store_id}의 {_iso(request.start_at)}부터 "
                        f"{_iso(request.end_at)}까지 데이터를 분석해 현재 직원 "
                        f"{request.current_staff_count}명, 최대 {request.max_staff_count}명 "
                        "범위에서 행사 인력안을 제안해줘."
                    ))],
                )
            ]
            for _ in range(MAX_AGENT_TURNS):
                response = self._model_client.models.generate_content(
                    model=self._settings.gemini_model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        tools=[
                            get_store_operating_summary,
                            get_hourly_timeline,
                            compare_staffing_options,
                        ],
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(
                            disable=True,
                        ),
                        temperature=0.1,
                    ),
                )
                calls = response.function_calls or []
                if not calls:
                    model_text = (response.text or "").strip()
                    break
                content = response.candidates[0].content
                contents.append(content)
                response_parts: list[Any] = []
                for call in calls:
                    yield event(
                        "tool_started",
                        {
                            "get_store_operating_summary": "매장 운영 데이터 조회",
                            "get_hourly_timeline": "피크 주문 시간대 탐지",
                            "compare_staffing_options": "동일 수요 직원 비교 실행",
                        }.get(call.name, call.name),
                        status="running",
                        tool_name=call.name,
                    )
                    result = execute_tool(call.name)
                    yield event(
                        "tool_completed",
                        {
                            "get_store_operating_summary": "매장 운영 데이터 확인 완료",
                            "get_hourly_timeline": "피크 주문 시간대 확인 완료",
                            "compare_staffing_options": (
                                f"직원 1~{request.max_staff_count}명 탐색 완료"
                            ),
                        }.get(call.name, call.name),
                        status="completed",
                        tool_name=call.name,
                        evidence=result,
                    )
                    response_parts.append(types.Part.from_function_response(
                        name=call.name,
                        response={"result": result},
                    ))
                contents.append(types.Content(role="user", parts=response_parts))
            if comparison is None:
                raise RuntimeError("Agent did not complete the staffing comparison")
        except Exception as exc:
            logger.warning("운영 Agent를 규칙 기반으로 대체합니다: %s", exc, exc_info=True)
            source = "rule_fallback"
            yield event(
                "fallback_started",
                "AI 호출을 완료하지 못해 규칙 기반 분석으로 전환했습니다.",
                status="warning",
            )
            for tool_name, title in (
                ("get_store_operating_summary", "매장 운영 데이터 조회"),
                ("get_hourly_timeline", "피크 주문 시간대 탐지"),
                ("compare_staffing_options", "동일 수요 직원 비교 실행"),
            ):
                if tool_name == "get_store_operating_summary" and summary is not None:
                    continue
                if tool_name == "get_hourly_timeline" and profile is not None:
                    continue
                if tool_name == "compare_staffing_options" and comparison is not None:
                    continue
                yield event(
                    "tool_started",
                    title,
                    status="running",
                    tool_name=tool_name,
                )
                result = execute_tool(tool_name)
                yield event(
                    "tool_completed",
                    f"{title} 완료",
                    status="completed",
                    tool_name=tool_name,
                    evidence=result,
                )

        assert comparison is not None
        recommendation = _verified_recommendation(comparison)
        result = {
            "source": source,
            "model": self._settings.gemini_model if source == "gemini_tool_agent" else None,
            "model_summary": model_text,
            "store_id": request.store_id,
            "period": {
                "start_at": _iso(request.start_at),
                "end_at": _iso(request.end_at),
            },
            "trace": trace,
            "demand_profile": profile,
            "data_sources": (summary or {}).get("data_sources") or [],
            "comparison": comparison,
            "recommendation": recommendation,
            "limitations": [
                "합성·What-if 결과이며 실제 POS 실적이나 자동 인력 지시가 아닙니다.",
                "최종 운영안은 슈퍼바이저가 매장 상황과 함께 승인해야 합니다.",
            ],
        }
        yield event(
            "recommendation_ready",
            "검증된 운영 권장안을 생성했습니다.",
            status="completed",
            evidence=recommendation["evidence"],
        )
        yield event(
            "run_completed",
            "운영 분석이 완료되었습니다.",
            status="completed",
            result=result,
        )
