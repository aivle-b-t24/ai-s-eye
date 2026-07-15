from typing import Any

import pytest

from app.router import QuestionRouter, QuestionType, classify
from app.tools import StoreTools


class FakeTools(StoreTools):
    """어떤 Tool이 불렸는지만 기록한다. HTTP는 타지 않는다."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def close(self) -> None:
        return None

    def get_store_state(self, store_id: str | None = None) -> dict[str, Any]:
        self.calls.append("state")
        return {"ok": True, "visible_person_count": 5, "queue_count_estimate": 2}

    def get_eta(self, store_id: str | None = None) -> dict[str, Any]:
        self.calls.append("eta")
        return {"ok": True, "estimated_wait_minutes": 6}

    def get_menus(
        self,
        store_id: str | None = None,
        menu_name: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append("menus")
        return {"ok": True, "menus": []}

    def get_policies(self, store_id: str | None = None) -> dict[str, Any]:
        self.calls.append("policies")
        return {"ok": True, "policies": []}


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("아메리카노 얼마예요?", QuestionType.MENU),
        ("치즈케이크 있나요?", QuestionType.MENU),
        ("지금 품절된 메뉴 있어요?", QuestionType.MENU),
        ("지금 몇 명 있나요?", QuestionType.STATE),
        ("매장 많이 붐비나요?", QuestionType.STATE),
        ("자리 있어요?", QuestionType.STATE),
        ("얼마나 기다려야 해요?", QuestionType.ETA),
        ("몇 분이나 걸려요?", QuestionType.ETA),
        ("몇 시까지 해요?", QuestionType.POLICY),
        ("주차 되나요?", QuestionType.POLICY),
        ("환불 가능한가요?", QuestionType.POLICY),
        ("강아지 데려가도 되나요?", QuestionType.POLICY),
        ("사장님 성함이 뭐예요?", QuestionType.UNKNOWN),
    ],
)
def test_classify_question_type(question: str, expected: QuestionType) -> None:
    assert classify(question) == expected


@pytest.mark.parametrize(
    ("question", "expected_tool"),
    [
        ("아메리카노 얼마예요?", "menus"),
        ("지금 몇 명 있나요?", "state"),
        ("얼마나 기다려야 해요?", "eta"),
        ("주차 되나요?", "policies"),
    ],
)
def test_router_calls_matching_tool(question: str, expected_tool: str) -> None:
    tools = FakeTools()
    router = QuestionRouter(tools)

    router.handle(question)

    assert tools.calls == [expected_tool]


def test_menu_question_does_not_call_other_tools() -> None:
    tools = FakeTools()
    router = QuestionRouter(tools)

    router.handle("품절된 메뉴 알려주세요")

    assert tools.calls == ["menus"]


def test_policy_question_is_marked_as_pending_rag() -> None:
    tools = FakeTools()
    router = QuestionRouter(tools)

    answer = router.handle("영업시간이 어떻게 되나요?")

    assert answer["question_type"] == "policy"
    assert answer["pending"] == "rag"
    assert answer["note"]


def test_unknown_question_falls_back_to_state_with_note() -> None:
    tools = FakeTools()
    router = QuestionRouter(tools)

    answer = router.handle("사장님 성함이 뭐예요?")

    assert answer["question_type"] == "unknown"
    assert answer["note"]
    assert tools.calls == ["state"]


def test_handle_keeps_original_question_and_tool_result() -> None:
    tools = FakeTools()
    router = QuestionRouter(tools)

    answer = router.handle("얼마나 기다려야 해요?")

    assert answer["question"] == "얼마나 기다려야 해요?"
    assert answer["tool"] == "eta"
    assert answer["result"]["estimated_wait_minutes"] == 6
