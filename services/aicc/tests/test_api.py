import json
import base64
from typing import Any, Callable

import httpx
from fastapi.testclient import TestClient

import aicc.api as api
from aicc.client import StoreApiClient
from aicc.scene_detection import (
    SceneSuggestionResponse,
    SceneSuggestionUnavailableError,
)


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
         "summary": "점심 혼잡", "probable_cause": "인근 직장인 점심 수요로 추정됩니다.",
         "evidence": {"peak_visible_person_count": 28}, "recommendation": "인력 보강"},
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
    # 추정 원인이 response_model에서 안 잘리고 그대로 나온다
    s1 = next(i for i in data["insights"] if i["store_id"] == "store-001")
    assert s1["probable_cause"] == "인근 직장인 점심 수요로 추정됩니다."


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



def test_scene_suggestion_ok(monkeypatch) -> None:
    expected = SceneSuggestionResponse(
        store_id="store-001",
        camera_id="store-001-cam1",
        model="yoloe-26s-seg.pt",
        objects=[
            {
                "id": "yolo-table-1",
                "type": "table",
                "label": "YOLO 테이블 1",
                "polygon": [
                    {"x": 100, "y": 100},
                    {"x": 300, "y": 100},
                    {"x": 300, "y": 300},
                    {"x": 100, "y": 300},
                ],
            }
        ],
        detections=[{"type": "table", "label": "YOLO 테이블 1", "confidence": 0.9}],
        warnings=["사람이 확인해야 합니다."],
    )
    monkeypatch.setattr(api, "generate_scene_suggestion", lambda req: expected)
    png = base64.b64encode(b"\x89PNG\r\n\x1a\nminimal").decode()
    tc = TestClient(api.app)

    response = tc.post(
        "/scene-suggestions",
        json={
            "store_id": "store-001",
            "camera_id": "store-001-cam1",
            "image_base64": png,
            "mime_type": "image/png",
            "image_width": 1920,
            "image_height": 1080,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["objects"][0]["type"] == "table"
    assert body["seat_anchors"] == []


def test_scene_suggestion_rejects_camera_from_other_store(monkeypatch) -> None:
    monkeypatch.setattr(api, "generate_scene_suggestion", lambda req: None)
    png = base64.b64encode(b"\x89PNG\r\n\x1a\nminimal").decode()
    tc = TestClient(api.app)

    response = tc.post(
        "/scene-suggestions",
        json={
            "store_id": "store-001",
            "camera_id": "store-002-cam1",
            "image_base64": png,
            "mime_type": "image/png",
            "image_width": 1920,
            "image_height": 1080,
        },
    )

    assert response.status_code == 422


def test_scene_suggestion_worker_failure_returns_503(monkeypatch) -> None:
    def _raise(_req):
        raise SceneSuggestionUnavailableError("connection refused")

    monkeypatch.setattr(api, "generate_scene_suggestion", _raise)
    png = base64.b64encode(b"\x89PNG\r\n\x1a\nminimal").decode()
    tc = TestClient(api.app)

    response = tc.post(
        "/scene-suggestions",
        json={
            "store_id": "store-001",
            "camera_id": "store-001-cam1",
            "image_base64": png,
            "mime_type": "image/png",
            "image_width": 1920,
            "image_height": 1080,
        },
    )

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["error"] == "scene_suggestion_unavailable"
    assert "장면 초안을 생성하지 못했습니다" in detail["message"]


# --- 챗봇 (/chat) ---


class FakeAgent:
    """StoreAgent 대역. ask()가 정해둔 답을 돌려준다."""

    def __init__(self, reply: dict[str, Any]) -> None:
        self._reply = reply
        self.seen: dict[str, Any] = {}

    def ask(self, question: str, store_id: str | None = None) -> dict[str, Any]:
        self.seen = {"question": question, "store_id": store_id}
        return self._reply


def test_chat_ok() -> None:
    agent = FakeAgent({"question": "지금 붐벼?", "answer": "현재 5명 있습니다.", "source": "gemini"})
    tc = TestClient(api.app)
    tc.app.state.agent = agent
    r = tc.post("/chat", json={"question": "지금 붐벼?", "store_id": "store-001"})
    assert r.status_code == 200
    data = r.json()
    assert data["answer"] == "현재 5명 있습니다."
    assert data["source"] == "gemini"
    assert agent.seen == {"question": "지금 붐벼?", "store_id": "store-001"}


def test_chat_fallback_source() -> None:
    agent = FakeAgent({"question": "메뉴?", "answer": "아메리카노 4500원", "source": "keyword_fallback"})
    tc = TestClient(api.app)
    tc.app.state.agent = agent
    r = tc.post("/chat", json={"question": "메뉴?"})
    assert r.status_code == 200
    assert r.json()["source"] == "keyword_fallback"


def test_chat_empty_question_returns_422() -> None:
    tc = TestClient(api.app)
    tc.app.state.agent = FakeAgent({})
    r = tc.post("/chat", json={"question": ""})  # 빈 질문
    assert r.status_code == 422


def test_chat_too_long_question_returns_422() -> None:
    tc = TestClient(api.app)
    tc.app.state.agent = FakeAgent({})
    r = tc.post("/chat", json={"question": "가" * 501})  # 500자 초과
    assert r.status_code == 422


def test_chat_blank_question_returns_422() -> None:
    """공백만 있는 질문도 막는다."""
    tc = TestClient(api.app)
    tc.app.state.agent = FakeAgent({})
    r = tc.post("/chat", json={"question": "   "})
    assert r.status_code == 422


class RaisingAgent:
    def ask(self, question: str, store_id: str | None = None) -> dict[str, Any]:
        raise RuntimeError("예상 밖 오류")


def test_chat_agent_error_returns_503_not_500() -> None:
    """agent가 예상 밖 예외를 던져도 500이 아니라 깔끔한 503을 준다."""
    tc = TestClient(api.app)
    tc.app.state.agent = RaisingAgent()
    r = tc.post("/chat", json={"question": "테스트"})
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "chat_unavailable"


def test_insights_cors_preflight() -> None:
    tc = TestClient(api.app)
    response = tc.options(
        "/insights",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
