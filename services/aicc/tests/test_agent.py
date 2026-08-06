from typing import Any, Callable

import httpx

from aicc.agent import MAX_TOOL_CALLS, SYSTEM_PROMPT, StoreAgent
from aicc.client import StoreApiClient
from aicc.tools import StoreTools


def test_system_prompt_has_policy_focus_rule() -> None:
    """정책 답변을 관련 항목만/나열 금지로 좁히는 규칙이 살아있어야 한다."""
    assert "나열하지 않는다" in SYSTEM_PROMPT  # 전체 나열 금지
    assert "관련된 항목만" in SYSTEM_PROMPT  # 관련 항목만 답변
    assert "되물어" in SYSTEM_PROMPT  # 포괄적 질문은 되물어 범위 좁히기


def test_system_prompt_has_answer_format_rules() -> None:
    """읽기 좋은 답변 형식(불릿·참고·마크다운 금지) 규칙이 살아있어야 한다."""
    assert "• " in SYSTEM_PROMPT  # 불릿 형식 안내
    assert "⚠️ 참고" in SYSTEM_PROMPT  # 참고 한 줄 안내
    assert "마크다운 기호는 쓰지 않는다" in SYSTEM_PROMPT  # 별표 등 화면에 깨지는 기호 금지


def test_system_prompt_answers_only_what_is_asked() -> None:
    """물어본 것만 답하는 규칙(메뉴 물으면 품절은 안 붙임)이 살아있어야 한다."""
    assert "물어본 것만 답한다" in SYSTEM_PROMPT
    assert "⚠️ 참고에 넣지 않는다" in SYSTEM_PROMPT  # 품절은 참고에도 안 붙임


def test_system_prompt_bundles_congestion_stats() -> None:
    """혼잡도 질문은 인원·대기·예상 대기시간을 함께 안내하도록 지시한다."""
    assert "get_wait_time" in SYSTEM_PROMPT
    assert "예상 대기시간" in SYSTEM_PROMPT


def test_system_prompt_deflects_off_topic_without_revealing_ai() -> None:
    """범위 밖·정체 질문에 'AI/구글'이라 밝히지 않고 매장 안내로 넘기는 규칙."""
    assert "언어 모델" in SYSTEM_PROMPT  # 자신을 언어모델/AI로 소개하지 말라는 규칙
    assert "매장 안내만 도와드릴 수 있어요" in SYSTEM_PROMPT


def test_tidy_markdown_normalizes_bullets_and_bold() -> None:
    """모델이 마크다운을 섞어 써도 화면에서 깨지지 않게 정리한다."""
    from aicc.agent import _tidy_markdown

    # '*'/'-' 불릿 → '•'
    assert _tidy_markdown("품절 메뉴\n* 아메리카노\n- 라떼") == "품절 메뉴\n• 아메리카노\n• 라떼"
    # 들여쓴 불릿도 유지하며 기호만 교체
    assert _tidy_markdown("  * 항목") == "  • 항목"
    # 굵게 기호 제거
    assert _tidy_markdown("**아메리카노**는 4500원") == "아메리카노는 4500원"
    # 이미 '•'면 그대로 둔다
    assert _tidy_markdown("• 아메리카노") == "• 아메리카노"


def test_gemini_answer_is_tidied() -> None:
    """ask()가 돌려주는 답변에서 마크다운 불릿이 '•'로 정리돼 나온다."""
    with agent_for(responder(200, menus_body())) as agent:
        agent._client = FakeGemini(text="품절 메뉴\n* 아메리카노\n* 라떼")
        result = agent.ask("품절 메뉴 있어?")

    assert "* 아메리카노" not in result["answer"]
    assert "• 아메리카노" in result["answer"]


def menus_body() -> dict[str, Any]:
    return {
        "store_id": "store-001",
        "data_source": "mock",
        "menus": [
            {
                "menu_id": "americano",
                "category": "coffee",
                "name": "아메리카노",
                "price": 4500,
                "prep_minutes": 3,
                "available": True,
                "sold_out_reason": None,
            }
        ],
    }


def responder(status_code: int, body: Any) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=body)

    return handler


def agent_for(handler: Callable[[httpx.Request], httpx.Response]) -> StoreAgent:
    """가짜 API로 백업된 StoreAgent. Gemini 클라이언트는 각 테스트에서 정한다."""
    tools = StoreTools(StoreApiClient(transport=httpx.MockTransport(handler)))
    return StoreAgent(tools=tools)


class FakeResponse:
    def __init__(self, text: str | None) -> None:
        self.text = text


class FakeModels:
    """google-genai의 client.models를 흉내낸다. 넘겨받은 값을 capture에 담아둔다."""

    def __init__(self, text: str | None, error: Exception | None, capture: dict[str, Any]) -> None:
        self._text = text
        self._error = error
        self._capture = capture

    def generate_content(self, *, model: str, contents: str, config: Any) -> FakeResponse:
        self._capture["model"] = model
        self._capture["contents"] = contents
        self._capture["config"] = config
        if self._error is not None:
            raise self._error
        return FakeResponse(self._text)


class FakeGemini:
    def __init__(
        self,
        text: str | None = None,
        error: Exception | None = None,
        capture: dict[str, Any] | None = None,
    ) -> None:
        self.models = FakeModels(text, error, capture if capture is not None else {})


# --- 대체 경로(fallback): Gemini를 못 쓸 때 키워드 방식으로 넘어가는가 ---


def test_falls_back_to_keywords_when_client_missing() -> None:
    with agent_for(responder(200, menus_body())) as agent:
        agent._client = None
        result = agent.ask("메뉴 알려줘")

    assert result["source"] == "keyword_fallback"
    assert result["result"]["question_type"] == "menu"


def test_falls_back_when_gemini_errors() -> None:
    with agent_for(responder(200, menus_body())) as agent:
        agent._client = FakeGemini(error=RuntimeError("boom"))
        result = agent.ask("메뉴 알려줘")

    assert result["source"] == "keyword_fallback"
    # Gemini가 죽어도 raw 데이터가 아니라 사람이 읽는 문장을 준다.
    assert isinstance(result["answer"], str) and result["answer"]
    assert "아메리카노" in result["answer"]
    assert result["reason"]


def test_fallback_answer_is_readable_sentence_by_tool() -> None:
    """Gemini 없이도 도구별로 읽을 수 있는 문장을 만든다."""
    from aicc.agent import _fallback_answer

    # 매장 상태
    s = _fallback_answer({"tool": "state", "result": {"ok": True, "visible_person_count": 5, "queue_count_estimate": 2}})
    assert "5명" in s and "2명" in s
    # 대기시간
    e = _fallback_answer({"tool": "eta", "result": {"ok": True, "estimated_wait_minutes": 6}})
    assert "6분" in e
    # 주문
    o = _fallback_answer({"tool": "order", "result": {"ok": True, "status_message": "접수되었습니다."}})
    assert o == "접수되었습니다."
    # 오류(ok=False)면 message 그대로
    f = _fallback_answer({"tool": "state", "result": {"ok": False, "message": "매장 시스템에 연결하지 못했습니다."}})
    assert f == "매장 시스템에 연결하지 못했습니다."


def test_fallback_menu_and_policy_use_bullets() -> None:
    """Gemini 없이도 메뉴·정책 fallback이 '•' 불릿 형식으로 나온다(Gemini 답변과 통일)."""
    from aicc.agent import _fallback_answer

    m = _fallback_answer({"tool": "menu", "result": {"ok": True, "menus": [
        {"name": "아메리카노", "price": 4500, "available": True},
        {"name": "라떼", "price": 5000, "available": False},
    ]}})
    assert "• 아메리카노: 4500원" in m
    assert "• 라떼: 5000원 (품절)" in m
    # 정책이 여러 개면 불릿, 하나면 내용만
    p = _fallback_answer({"tool": "policy", "result": {"ok": True, "policies": [
        {"title": "주차", "content": "지하 주차장 이용 가능"},
        {"title": "와이파이", "content": "무료 제공"},
    ]}})
    assert "• 주차: 지하 주차장 이용 가능" in p
    one = _fallback_answer({"tool": "policy", "result": {"ok": True, "policies": [
        {"title": "주차", "content": "지하 주차장 이용 가능"},
    ]}})
    assert one == "지하 주차장 이용 가능"


def test_falls_back_when_gemini_returns_empty() -> None:
    with agent_for(responder(200, menus_body())) as agent:
        agent._client = FakeGemini(text="   ")
        result = agent.ask("메뉴 알려줘")

    assert result["source"] == "keyword_fallback"


# --- 정상 경로: Gemini가 답을 주면 그대로 돌려주는가 ---


def test_returns_gemini_answer() -> None:
    with agent_for(responder(200, menus_body())) as agent:
        agent._client = FakeGemini(text="아메리카노는 4500원입니다.")
        result = agent.ask("아메리카노 얼마예요?")

    assert result["source"] == "gemini"
    assert result["answer"] == "아메리카노는 4500원입니다."


def test_ask_includes_suggestions() -> None:
    """응답에 이어서 물어볼 추천 질문(suggestions)이 담긴다."""
    with agent_for(responder(200, menus_body())) as agent:
        agent._client = FakeGemini(text="아메리카노는 4500원입니다.")
        result = agent.ask("아메리카노 얼마예요?")

    assert isinstance(result["suggestions"], list) and result["suggestions"]


def test_suggest_questions_by_type() -> None:
    """추천 질문은 질문 종류에 맞게, 우리가 답할 수 있는 것으로 나온다."""
    from aicc.agent import suggest_questions

    # 메뉴를 물으면 메뉴 추천은 빼고 다른 종류를 권한다(중복 방지)
    s = suggest_questions("메뉴 알려줘")
    assert isinstance(s, list) and 1 <= len(s) <= 3
    assert "메뉴 가격 알려줘" not in s
    # 영업시간(정책)을 물으면 영업시간을 다시 추천하지 않는다
    assert "영업시간 언제까지야?" not in suggest_questions("영업시간 언제까지야?")
    # 분류 안 되는 질문은 기본(앞 두 종류) 추천으로
    assert suggest_questions("사장님 성함이 뭐예요") == ["메뉴 가격 알려줘", "지금 매장 붐벼?"]


def test_fallback_also_includes_suggestions() -> None:
    """Gemini가 죽어 fallback으로 가도 추천 질문이 담긴다."""
    with agent_for(responder(200, menus_body())) as agent:
        agent._client = FakeGemini(error=RuntimeError("boom"))
        result = agent.ask("메뉴 알려줘")

    assert result["source"] == "keyword_fallback"
    assert isinstance(result["suggestions"], list) and result["suggestions"]


# --- 무한루프 방지: 도구 자동호출 5회 제한이 실제로 전달되는가 ---


def test_max_tool_calls_limit_is_applied() -> None:
    capture: dict[str, Any] = {}
    with agent_for(responder(200, menus_body())) as agent:
        agent._client = FakeGemini(text="답변", capture=capture)
        agent.ask("아메리카노 얼마예요?")

    afc = capture["config"].automatic_function_calling
    assert afc.maximum_remote_calls == MAX_TOOL_CALLS == 5


# --- 도구 등록: Gemini에 넘기는 도구 5개가 다 있는가 ---


def test_registers_all_five_tools() -> None:
    with agent_for(responder(200, menus_body())) as agent:
        functions = agent._tool_functions("store-001")

    names = {fn.__name__ for fn in functions}
    assert names == {
        "get_store_state",
        "get_wait_time",
        "get_menus",
        "get_policies",
        "get_order_status",
    }


def test_registered_tool_calls_real_api() -> None:
    with agent_for(responder(200, menus_body())) as agent:
        functions = {fn.__name__: fn for fn in agent._tool_functions("store-001")}
        result = functions["get_menus"]()

    assert result["ok"] is True
    assert result["menus"][0]["name"] == "아메리카노"
