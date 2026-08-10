from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from google.genai import types

from aicc.operations_agent import (
    OperationsAgentRequest,
    OperationsDecisionAgent,
    build_peak_arrival_profile,
)


def _comparison() -> dict[str, Any]:
    one = {
        "visitors": 100,
        "completed_orders": 78,
        "abandoned_orders": 18,
        "in_progress_orders": 4,
        "average_wait_minutes": 8.2,
        "max_queue": 14,
        "staff_utilization_percent": 98,
        "seat_utilization_percent": 55,
    }
    two = {
        **one,
        "completed_orders": 94,
        "abandoned_orders": 3,
        "in_progress_orders": 3,
        "average_wait_minutes": 3.1,
        "max_queue": 6,
        "staff_utilization_percent": 81,
    }
    normal = {**one, "visitors": 60, "completed_orders": 58, "abandoned_orders": 0}
    return {
        "comparison_id": "comparison-test",
        "event_demand_trace_id": "demand-shared",
        "base_trace_id": "demand-base",
        "normal_one": {"metrics": normal, "events": [], "frames": []},
        "event_one": {"metrics": one, "events": [], "frames": [], "demand_trace_id": "demand-shared"},
        "event_two": {"metrics": two, "events": [], "frames": [], "demand_trace_id": "demand-shared"},
    }


class FakeStoreClient:
    def get_store_summary(self, *_: Any) -> dict[str, Any]:
        return {
            "stores": [{
                "store_id": "store-001",
                "traffic_summary": {
                    "average_visible_person_count": 8,
                    "peak_visible_person_count": 21,
                    "peak_queue_count_estimate": 9,
                },
                "order_summary": {
                    "total_order_count": 300,
                    "data_sources": ["synthetic_order_simulator"],
                },
            }],
        }

    def get_store_timeline(self, *_: Any) -> dict[str, Any]:
        return {
            "points": [
                {"start_at": "2026-08-01T02:00:00Z", "order_count": 18},
                {"start_at": "2026-08-01T03:00:00Z", "order_count": 34},
                {"start_at": "2026-08-01T04:00:00Z", "order_count": 25},
            ],
        }

    def compare_operations(self, payload: dict[str, Any]) -> dict[str, Any]:
        assert payload["arrival_profile"][1]["arrivals_per_hour"] == 34
        return _comparison()


class ToolCallingModels:
    def __init__(self) -> None:
        self.calls = 0

    def generate_content(self, **_: Any) -> Any:
        self.calls += 1
        if self.calls == 1:
            calls = [
                SimpleNamespace(name="get_store_operating_summary", args={}),
                SimpleNamespace(name="get_hourly_timeline", args={}),
            ]
        elif self.calls == 2:
            calls = [SimpleNamespace(name="compare_staffing_options", args={})]
        else:
            return SimpleNamespace(function_calls=[], text='{"summary":"직원 2명 권장"}')
        content = types.Content(
            role="model",
            parts=[types.Part.from_function_call(name=call.name, args={}) for call in calls],
        )
        return SimpleNamespace(
            function_calls=calls,
            text="",
            candidates=[SimpleNamespace(content=content)],
        )


class ToolCallingClient:
    def __init__(self) -> None:
        self.models = ToolCallingModels()


class RaisingModels:
    def generate_content(self, **_: Any) -> Any:
        raise RuntimeError("quota")


class RaisingClient:
    models = RaisingModels()


class RepeatingToolModels:
    def __init__(self) -> None:
        self.calls = 0

    def generate_content(self, **_: Any) -> Any:
        self.calls += 1
        call = SimpleNamespace(name="get_store_operating_summary", args={})
        content = types.Content(
            role="model",
            parts=[types.Part.from_function_call(name=call.name, args={})],
        )
        return SimpleNamespace(
            function_calls=[call],
            text="",
            candidates=[SimpleNamespace(content=content)],
        )


class RepeatingToolClient:
    def __init__(self) -> None:
        self.models = RepeatingToolModels()


def _request() -> OperationsAgentRequest:
    return OperationsAgentRequest(
        store_id="store-001",
        start_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        end_at=datetime(2026, 8, 2, tzinfo=timezone.utc),
    )


def test_peak_profile_uses_kst_hourly_orders() -> None:
    profile = build_peak_arrival_profile(FakeStoreClient().get_store_timeline(), 180)

    assert profile["source"] == "selected_period_hourly_orders"
    assert profile["window_label"] == "11:00~14:00 KST"
    assert profile["rates"] == [18, 34, 25]


def test_peak_profile_uses_presentation_fallback_without_orders() -> None:
    profile = build_peak_arrival_profile({"points": []}, 180)

    assert profile["source"] == "presentation_fallback"
    assert profile["window_label"] == "11:00~14:00 KST"
    assert profile["rates"] == [19.2, 30, 24]


def test_agent_streams_actual_tool_trace_and_verified_recommendation() -> None:
    agent = OperationsDecisionAgent(FakeStoreClient(), ToolCallingClient())
    events = list(agent.stream(_request()))

    assert [item["event"] for item in events].count("tool_started") == 3
    completed = events[-1]
    assert completed["event"] == "run_completed"
    assert completed["result"]["source"] == "gemini_tool_agent"
    assert completed["result"]["recommendation"]["recommended_staff_count"] == 2
    assert completed["result"]["comparison"]["event_demand_trace_id"] == "demand-shared"


def test_agent_marks_rule_fallback_when_gemini_fails() -> None:
    agent = OperationsDecisionAgent(FakeStoreClient(), RaisingClient())
    events = list(agent.stream(_request()))

    assert any(item["event"] == "fallback_started" for item in events)
    assert events[-1]["result"]["source"] == "rule_fallback"
    assert events[-1]["result"]["model"] is None


def test_agent_stops_gemini_after_five_turns_and_finishes_with_rules() -> None:
    model_client = RepeatingToolClient()
    agent = OperationsDecisionAgent(FakeStoreClient(), model_client)
    events = list(agent.stream(_request()))

    assert model_client.models.calls == 5
    assert any(item["event"] == "fallback_started" for item in events)
    assert events[-1]["event"] == "run_completed"
    assert events[-1]["result"]["source"] == "rule_fallback"
