import json
from typing import Any, Callable

import httpx
from fastapi.testclient import TestClient

import aicc.api as api
from aicc.client import StoreApiClient


def summary_body() -> dict[str, Any]:
    """공통 집계 API(GET /api/stores/summary) 형식의 두 매장 응답."""
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
                "order_summary": {"total_order_count": 3, "latest_status_counts": {}, "top_menu_items": []},
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
                "order_summary": {"total_order_count": 3, "latest_status_counts": {}, "top_menu_items": []},
                "video_summary": {"latest_quality_status": "normal", "quality_issue_count": 0},
            },
        ],
    }


FAKE_INSIGHTS = {
    "insights": [
        {"store_id": "store-001", "insight_type": "congestion", "severity": "high",
         "summary": "점심 혼잡", "evidence": {"peak_visible_person_count": 28}, "recommendation": "인력 보강"},
        {"store_id": "store-002", "insight_type": "afternoon_demand", "severity": "medium",
         "summary": "오후 수요", "evidence": {"peak_visible_person_count": 22}, "recommendation": "재고 보충"},
    ],
    "comparison": {"summary": "001 점심 vs 002 오후", "recommendation": "매장별 운영"},
}


# --- 가짜 Gemini ---


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeModels:
    def __init__(self, text: str) -> None:
        self._text = text

    def generate_content(self, **_: Any) -> FakeResponse:
        return FakeResponse(self._text)


class FakeGemini:
    def __init__(self, text: str) -> None:
        self.models = FakeModels(text)


def client_with(
    handler: Callable[[httpx.Request], httpx.Response],
    monkeypatch: Any,
    gemini_text: str | None = json.dumps(FAKE_INSIGHTS),
) -> TestClient:
    """가짜 집계 API + 가짜 Gemini로 테스트 클라이언트를 만든다.

    gemini_text=None이면 Gemini를 못 만드는 상황(→ 분석 오류)을 흉내낸다.
    """
    # build_client를 가짜로: 텍스트가 있으면 FakeGemini, 없으면 None(=분석 실패)
    fake_client = FakeGemini(gemini_text) if gemini_text is not None else None
    monkeypatch.setattr("aicc.franchise_insights.build_client", lambda: fake_client)

    tc = TestClient(api.app)
    tc.app.state.client = StoreApiClient(transport=httpx.MockTransport(handler))
    return tc


def ok_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=summary_body())


# --- 정상 응답 ---


def test_insights_ok(monkeypatch) -> None:
    tc = client_with(ok_handler, monkeypatch=monkeypatch)
    r = tc.post("/insights", json={})
    assert r.status_code == 200
    data = r.json()
    ids = {i["store_id"] for i in data["insights"]}
    assert ids == {"store-001", "store-002"}
    assert data["comparison"]["summary"]


def test_insights_ok_with_period(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=summary_body())

    tc = client_with(handler, monkeypatch=monkeypatch)
    r = tc.post("/insights", json={"start_at": "2026-07-21T00:00:00Z", "end_at": "2026-07-22T00:00:00Z"})
    assert r.status_code == 200
    assert "start_at" in seen["url"] and "end_at" in seen["url"]  # 기간이 집계 API로 전달됨


# --- 오류 구분 ---


def test_store_api_error_returns_502(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "down"})  # 집계 API 장애

    tc = client_with(handler, monkeypatch=monkeypatch)
    r = tc.post("/insights", json={})
    assert r.status_code == 502
    assert r.json()["detail"]["error"] == "store_api_error"


def test_gemini_error_returns_503(monkeypatch) -> None:
    tc = client_with(ok_handler, gemini_text=None, monkeypatch=monkeypatch)
    r = tc.post("/insights", json={})
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "insights_unavailable"


def test_bad_period_returns_422(monkeypatch) -> None:
    tc = client_with(ok_handler, monkeypatch=monkeypatch)
    # 시작이 끝보다 뒤 -> 검증 실패
    r = tc.post("/insights", json={"start_at": "2026-07-22T00:00:00Z", "end_at": "2026-07-21T00:00:00Z"})
    assert r.status_code == 422


def test_healthz() -> None:
    tc = TestClient(api.app)
    assert tc.get("/healthz").json() == {"status": "ok"}
