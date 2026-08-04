"""카카오 스킬 웹훅(/kakao/skill) 테스트.

두뇌(StoreAgent)는 FakeAgent로 대역을 세우고, 여기서는 카카오 형식 변환과
'어떤 상황에도 스킬 형식 200' 규약만 검증한다.
"""

from typing import Any

from fastapi.testclient import TestClient

import aicc.api as api
import aicc.config as config
from aicc.kakao import (
    KakaoSkillPayload,
    build_skill_response,
    coerce_payload,
    extract_utterance,
    resolve_store_id,
)


# 카카오 i 오픈빌더 스킬 테스트가 실제로 보내는 형태(널 필드 다수 포함).
def kakao_sample_payload(utterance: Any) -> dict[str, Any]:
    return {
        "intent": {"id": "abc", "name": "블록 이름"},
        "userRequest": {
            "timezone": "Asia/Seoul",
            "params": {"ignoreMe": "true"},
            "block": {"id": "abc", "name": "블록 이름"},
            "utterance": utterance,
            "lang": None,
            "user": {"id": "u1", "type": "botUserKey", "properties": {}},
        },
        "bot": {"id": "b1", "name": "봇 이름"},
        "action": {
            "id": "act",
            "name": "스킬",
            "params": {},
            "detailParams": {},
            "clientExtra": None,
        },
    }


class FakeAgent:
    """StoreAgent 대역. ask()가 받은 인자를 기록하고 정해둔 답을 돌려준다."""

    def __init__(self, answer: str = "현재 5명 있습니다.") -> None:
        self._answer = answer
        self.seen: dict[str, Any] = {}
        self.called = False

    def ask(self, question: str, store_id: str | None = None) -> dict[str, Any]:
        self.called = True
        self.seen = {"question": question, "store_id": store_id}
        return {"question": question, "answer": self._answer, "source": "gemini"}


class RaisingAgent:
    def ask(self, question: str, store_id: str | None = None) -> dict[str, Any]:
        raise RuntimeError("두뇌 폭발")


def client_with(agent: Any) -> TestClient:
    tc = TestClient(api.app)
    tc.app.state.agent = agent
    return tc


def skill_request(utterance: str, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"userRequest": {"utterance": utterance}}
    if extra:
        body["action"] = extra
    return body


# --- 형식 변환 유닛 ---


def test_extract_utterance_strips() -> None:
    payload = KakaoSkillPayload.model_validate({"userRequest": {"utterance": "  붐벼?  "}})
    assert extract_utterance(payload) == "붐벼?"


def test_resolve_store_id_default_when_missing() -> None:
    payload = KakaoSkillPayload.model_validate({"userRequest": {"utterance": "안녕"}})
    assert resolve_store_id(payload, "store-001") == "store-001"


def test_resolve_store_id_from_client_extra() -> None:
    payload = KakaoSkillPayload.model_validate(
        {"userRequest": {"utterance": "안녕"}, "action": {"clientExtra": {"store_id": "store-002"}}}
    )
    assert resolve_store_id(payload, "store-001") == "store-002"


def test_resolve_store_id_from_detail_params_value() -> None:
    # detailParams는 {"value": ..., "origin": ...} 형태로 온다.
    payload = KakaoSkillPayload.model_validate(
        {
            "userRequest": {"utterance": "안녕"},
            "action": {"detailParams": {"store_id": {"origin": "2호점", "value": "store-002"}}},
        }
    )
    assert resolve_store_id(payload, "store-001") == "store-002"


def test_build_skill_response_shape() -> None:
    resp = build_skill_response("안녕하세요", [{"label": "메뉴", "action": "message", "messageText": "메뉴"}])
    assert resp["version"] == "2.0"
    assert resp["template"]["outputs"][0]["simpleText"]["text"] == "안녕하세요"
    assert resp["template"]["quickReplies"][0]["label"] == "메뉴"


def test_payload_ignores_unknown_fields() -> None:
    # 카카오가 필드를 늘려도 검증이 깨지지 않아야 한다.
    payload = KakaoSkillPayload.model_validate(
        {"userRequest": {"utterance": "붐벼?", "미래필드": 1}, "bot": {"id": "x"}, "intent": {"id": "y"}}
    )
    assert extract_utterance(payload) == "붐벼?"


def test_coerce_payload_handles_null_utterance() -> None:
    # utterance가 null이어도 예외 없이 빈 발화로 본다(422 방지 핵심).
    payload = coerce_payload(kakao_sample_payload(None))
    assert extract_utterance(payload) == ""


def test_coerce_payload_handles_full_sample_with_nulls() -> None:
    # 실제 오픈빌더 샘플 형태(널 필드 포함)에서 발화가 살아남는다.
    payload = coerce_payload(kakao_sample_payload("지금 붐비나요?"))
    assert extract_utterance(payload) == "지금 붐비나요?"


def test_coerce_payload_non_dict_returns_empty() -> None:
    for junk in (None, "문자열", [1, 2], 42):
        assert extract_utterance(coerce_payload(junk)) == ""


# --- 엔드포인트 ---


def test_kakao_skill_ok_passes_question_and_wraps_answer() -> None:
    agent = FakeAgent("현재 5명 있습니다.")
    tc = client_with(agent)
    r = tc.post("/kakao/skill", json=skill_request("지금 붐벼?"))
    assert r.status_code == 200
    data = r.json()
    assert data["version"] == "2.0"
    assert data["template"]["outputs"][0]["simpleText"]["text"] == "현재 5명 있습니다."
    assert data["template"]["quickReplies"]  # 자주 묻는 질문 버튼 포함
    # 발화가 그대로 두뇌에 전달되고, 매장은 기본값(store-001)
    assert agent.seen == {"question": "지금 붐벼?", "store_id": "store-001"}


def test_kakao_skill_empty_utterance_returns_greeting_without_calling_agent() -> None:
    agent = FakeAgent()
    tc = client_with(agent)
    r = tc.post("/kakao/skill", json=skill_request("   "))
    assert r.status_code == 200
    assert not agent.called  # 빈 발화면 두뇌를 부르지 않는다
    assert "안녕하세요" in r.json()["template"]["outputs"][0]["simpleText"]["text"]


def test_kakao_skill_real_sample_payload_returns_200() -> None:
    """오픈빌더 스킬 테스트가 보내는 널 포함 샘플로도 422가 아니라 200을 준다."""
    agent = FakeAgent("현재 8명 있습니다.")
    tc = client_with(agent)
    r = tc.post("/kakao/skill", json=kakao_sample_payload("지금 붐비나요?"))
    assert r.status_code == 200
    assert r.json()["template"]["outputs"][0]["simpleText"]["text"] == "현재 8명 있습니다."
    assert agent.seen["question"] == "지금 붐비나요?"


def test_kakao_skill_null_utterance_returns_greeting() -> None:
    """utterance=null(카카오 초기 진입 등)도 422 없이 인사로 응대한다."""
    agent = FakeAgent()
    tc = client_with(agent)
    r = tc.post("/kakao/skill", json=kakao_sample_payload(None))
    assert r.status_code == 200
    assert not agent.called
    assert "안녕하세요" in r.json()["template"]["outputs"][0]["simpleText"]["text"]


def test_kakao_skill_garbage_body_returns_200() -> None:
    """본문이 비거나 이상해도 스킬 형식 200을 유지한다."""
    tc = client_with(FakeAgent())
    r = tc.post("/kakao/skill", content=b"", headers={"Content-Type": "application/json"})
    assert r.status_code == 200
    assert r.json()["version"] == "2.0"


def test_kakao_skill_store_override() -> None:
    agent = FakeAgent()
    tc = client_with(agent)
    r = tc.post(
        "/kakao/skill",
        json=skill_request("붐벼?", clientExtra={"store_id": "store-002"}),
    )
    assert r.status_code == 200
    assert agent.seen["store_id"] == "store-002"


def test_kakao_skill_agent_error_returns_200_with_notice() -> None:
    """두뇌가 터져도 비-200이 아니라 정중한 스킬 200을 준다(카카오 규약)."""
    tc = client_with(RaisingAgent())
    r = tc.post("/kakao/skill", json=skill_request("붐벼?"))
    assert r.status_code == 200
    text = r.json()["template"]["outputs"][0]["simpleText"]["text"]
    assert "잠시 후" in text


def test_kakao_skill_empty_answer_falls_back_to_notice() -> None:
    tc = client_with(FakeAgent(answer=""))
    r = tc.post("/kakao/skill", json=skill_request("붐벼?"))
    assert r.status_code == 200
    text = r.json()["template"]["outputs"][0]["simpleText"]["text"]
    assert "잠시 후" in text


# --- 공유 토큰 ---


def _set_token(monkeypatch: Any, value: str | None) -> None:
    if value is None:
        monkeypatch.delenv("AICC_KAKAO_SKILL_TOKEN", raising=False)
    else:
        monkeypatch.setenv("AICC_KAKAO_SKILL_TOKEN", value)
    config.get_settings.cache_clear()


def test_kakao_skill_rejects_wrong_token(monkeypatch) -> None:
    _set_token(monkeypatch, "s3cret")
    try:
        tc = client_with(FakeAgent())
        r = tc.post("/kakao/skill", json=skill_request("붐벼?"))  # 토큰 없음
        assert r.status_code == 401
    finally:
        config.get_settings.cache_clear()


def test_kakao_skill_accepts_header_token(monkeypatch) -> None:
    _set_token(monkeypatch, "s3cret")
    try:
        agent = FakeAgent()
        tc = client_with(agent)
        r = tc.post(
            "/kakao/skill",
            json=skill_request("붐벼?"),
            headers={"X-Kakao-Skill-Token": "s3cret"},
        )
        assert r.status_code == 200
        assert agent.called
    finally:
        config.get_settings.cache_clear()


def test_kakao_skill_accepts_query_token(monkeypatch) -> None:
    _set_token(monkeypatch, "s3cret")
    try:
        tc = client_with(FakeAgent())
        r = tc.post("/kakao/skill?token=s3cret", json=skill_request("붐벼?"))
        assert r.status_code == 200
    finally:
        config.get_settings.cache_clear()
