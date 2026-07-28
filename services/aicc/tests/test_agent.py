from typing import Any, Callable

import httpx

from aicc.agent import MAX_TOOL_CALLS, StoreAgent
from aicc.client import StoreApiClient
from aicc.tools import StoreTools


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
    assert result["answer"] is None
    assert result["reason"]


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
