import json
from typing import Any

import pytest

from aicc.franchise_insights import (
    InsightsUnavailableError,
    _to_kst,
    build_prompt,
    generate_insights,
)


def summary() -> dict[str, Any]:
    """이도훈 집계 API(GET /api/stores/summary) 형식의 두 매장 샘플."""
    return {
        "schema_version": "1.0",
        "stores": [
            {
                "store_id": "store-001",
                "traffic_summary": {
                    "average_visible_person_count": 15.5,
                    "peak_visible_person_count": 28,
                    "peak_visible_person_count_at": "2026-07-22T03:00:00Z",
                    "average_queue_count_estimate": 3.0,
                    "peak_queue_count_estimate": 9,
                    "peak_queue_count_estimate_at": "2026-07-22T03:00:00Z",
                },
                "order_summary": {
                    "total_order_count": 3,
                    "latest_status_counts": {"received": 1, "preparing": 2},
                    "top_menu_items": [{"menu_id": "menu-001", "name": "아메리카노", "quantity": 5}],
                },
                "video_summary": {"latest_quality_status": "normal", "quality_issue_count": 0},
            },
            {
                "store_id": "store-002",
                "traffic_summary": {
                    "average_visible_person_count": 16.25,
                    "peak_visible_person_count": 22,
                    "peak_visible_person_count_at": "2026-07-22T05:00:00Z",
                    "average_queue_count_estimate": 1.75,
                    "peak_queue_count_estimate": 4,
                    "peak_queue_count_estimate_at": "2026-07-22T05:00:00Z",
                },
                "order_summary": {
                    "total_order_count": 3,
                    "latest_status_counts": {"received": 1, "completed": 1},
                    "top_menu_items": [{"menu_id": "menu-021", "name": "크루아상", "quantity": 2}],
                },
                "video_summary": {"latest_quality_status": "normal", "quality_issue_count": 0},
            },
        ],
    }


# 가짜 Gemini가 돌려줄 정답에 가까운 응답 (실제 Gemini 대신)
FAKE_OUTPUT = {
    "insights": [
        {
            "store_id": "store-001",
            "insight_type": "congestion",
            "severity": "high",
            "summary": "점심시간에 인원과 대기가 급증했습니다.",
            "evidence": {"peak_visible_person_count": 28, "peak_queue_count_estimate": 9},
            "recommendation": "점심 전 인력을 늘리세요.",
        },
        {
            "store_id": "store-002",
            "insight_type": "afternoon_demand",
            "severity": "medium",
            "summary": "오후에 방문과 베이커리 주문이 늘었습니다.",
            "evidence": {"peak_visible_person_count": 22},
            "recommendation": "오후 전 베이커리를 보충하세요.",
        },
    ],
    "comparison": {
        "summary": "store-001은 점심 혼잡, store-002는 오후 수요가 높습니다.",
        "recommendation": "매장별 피크에 맞춰 운영하세요.",
    },
}


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeModels:
    def __init__(self, payload: Any, capture: dict[str, Any]) -> None:
        self._payload = payload
        self._capture = capture

    def generate_content(self, *, model: str, contents: str, config: Any) -> FakeResponse:
        self._capture["contents"] = contents
        self._capture["config"] = config
        if isinstance(self._payload, Exception):
            raise self._payload
        return FakeResponse(self._payload)


class FakeGemini:
    def __init__(self, payload: Any, capture: dict[str, Any] | None = None) -> None:
        self.models = FakeModels(payload, capture if capture is not None else {})


# --- KST 변환 ---


def test_utc_peak_time_converts_to_kst_lunch() -> None:
    # 03:00 UTC == 12:00 KST (점심). 형식은 "YYYY-MM-DD HH:MM" (KST 접미사 없음)
    assert _to_kst("2026-07-22T03:00:00Z") == "2026-07-22 12:00"


def test_utc_peak_time_converts_to_kst_afternoon() -> None:
    # 05:00 UTC == 14:00 KST (오후)
    assert _to_kst("2026-07-22T05:00:00Z") == "2026-07-22 14:00"


def test_bad_time_returns_original() -> None:
    assert _to_kst("이상한값") == "이상한값"


# --- 프롬프트 (가드레일) ---


def test_prompt_uses_kst_not_raw_utc() -> None:
    p = build_prompt(summary())
    assert "2026-07-22 12:00" in p  # store-001 피크가 KST로 환산돼 들어감
    assert "2026-07-22T03:00:00Z" not in p  # 원본 UTC는 안 들어감


def test_prompt_has_both_stores_numbers() -> None:
    p = build_prompt(summary())
    assert "store-001" in p and "store-002" in p
    assert "28" in p and "22" in p  # 두 매장 피크 인원


def test_prompt_does_not_leak_expected_insights() -> None:
    """정답(expected_insights)이 프롬프트에 새지 않는다."""
    s = summary()
    s["expected_insights"] = [{"store_id": "store-001", "insight_type": "SECRET_ANSWER"}]
    p = build_prompt(s)
    assert "SECRET_ANSWER" not in p
    assert "expected_insights" not in p


# --- 생성 결과 ---


def test_generate_returns_insights_and_comparison() -> None:
    client = FakeGemini(json.dumps(FAKE_OUTPUT))
    result = generate_insights(summary(), client=client)
    assert "insights" in result and "comparison" in result
    ids = {i["store_id"] for i in result["insights"]}
    assert ids == {"store-001", "store-002"}


def test_finds_store001_congestion_and_store002_afternoon() -> None:
    """완료 기준: store-001 점심 혼잡, store-002 오후 수요."""
    client = FakeGemini(json.dumps(FAKE_OUTPUT))
    result = generate_insights(summary(), client=client)
    by_store = {i["store_id"]: i for i in result["insights"]}
    assert by_store["store-001"]["insight_type"] == "congestion"
    assert by_store["store-002"]["insight_type"] == "afternoon_demand"


def test_config_forces_json_output() -> None:
    capture: dict[str, Any] = {}
    client = FakeGemini(json.dumps(FAKE_OUTPUT), capture=capture)
    generate_insights(summary(), client=client)
    assert capture["config"].response_mime_type == "application/json"


def test_no_client_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # Gemini를 못 만드는 상황을 강제 (환경에 크레딧이 있어도 흔들리지 않게)
    monkeypatch.setattr("aicc.franchise_insights.build_client", lambda: None)
    with pytest.raises(InsightsUnavailableError):
        generate_insights(summary(), client=None)


def test_gemini_error_raises() -> None:
    client = FakeGemini(RuntimeError("boom"))
    with pytest.raises(InsightsUnavailableError):
        generate_insights(summary(), client=client)


def test_non_json_response_raises() -> None:
    client = FakeGemini("이건 JSON이 아님")
    with pytest.raises(InsightsUnavailableError):
        generate_insights(summary(), client=client)


@pytest.mark.parametrize("bad", [[], "문자열", {"period": {}}, {"stores": "리스트아님"}, None])
def test_malformed_summary_raises_cleanly(bad: Any) -> None:
    """집계 응답이 이상한 형식이면 500이 아니라 깔끔한 오류를 낸다."""
    client = FakeGemini(json.dumps(FAKE_OUTPUT))
    with pytest.raises(InsightsUnavailableError):
        generate_insights(bad, client=client)
