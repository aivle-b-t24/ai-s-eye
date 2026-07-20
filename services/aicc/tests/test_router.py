from typing import Any

import pytest

from aicc.router import QuestionRouter, QuestionType, classify
from aicc.tools import StoreTools


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
        ("몇 시까지 영업해요?", QuestionType.POLICY),
        ("아메리카노 가격이 얼마예요?", QuestionType.MENU),
        ("지금 사람이 많나요?", QuestionType.STATE),
        ("얼마나 기다려야 하나요?", QuestionType.ETA),
        ("포장 주문 가능한가요?", QuestionType.POLICY),
        ("주차할 수 있나요?", QuestionType.POLICY),
        ("바닐라 라떼 아직 판매하나요?", QuestionType.MENU),
        ("반려동물도 들어갈 수 있나요?", QuestionType.POLICY),
        ("키오스크로 주문할 수 있나요?", QuestionType.POLICY),
        ("아이랑 같이 가도 되나요?", QuestionType.POLICY),
        ("와이파이 되나요?", QuestionType.POLICY),
        ("예약할 수 있나요?", QuestionType.POLICY),
        ("단체로 20명 예약돼요?", QuestionType.POLICY),
        ("우유 알레르기 있는데 괜찮을까요?", QuestionType.POLICY),
        ("오트밀 우유로 바꿀 수 있어요?", QuestionType.POLICY),
        ("몇 명이서 가도 되나요?", QuestionType.POLICY),
        ("빨대 어디 있어요?", QuestionType.POLICY),
        ("얼마나 앉아 있어도 되나요?", QuestionType.POLICY),
        ("담배 피울 수 있나요?", QuestionType.POLICY),
        ("화장실 어디예요?", QuestionType.POLICY),
        ("포장했는데 매장에서 먹어도 돼요?", QuestionType.POLICY),
        ("지갑을 두고 간 것 같아요", QuestionType.POLICY),
        ("기프트 카드 있어요?", QuestionType.POLICY),
        ("테라스 있어요?", QuestionType.POLICY),
        ("지역화폐로 결제되나요?", QuestionType.POLICY),
        ("콘센트 있어요?", QuestionType.POLICY),
        ("지금 품절인 메뉴 있어요?", QuestionType.MENU),
        ("주문 취소할 수 있나요?", QuestionType.POLICY),
        ("라스트오더 몇 시예요?", QuestionType.POLICY),
        ("현금영수증 되나요?", QuestionType.POLICY),
        ("유아용 의자 있어요?", QuestionType.POLICY),
        ("케이크 가져가서 먹어도 돼요?", QuestionType.POLICY),
        ("지금 몇 명 있나요?", QuestionType.STATE),
        ("매장 많이 붐비나요?", QuestionType.STATE),
        ("자리 있어요?", QuestionType.STATE),
        ("치즈케이크 있나요?", QuestionType.MENU),
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


def test_unknown_question_calls_no_tool_and_says_so() -> None:
    tools = FakeTools()
    router = QuestionRouter(tools)

    answer = router.handle("사장님 성함이 뭐예요?")

    assert answer["question_type"] == "unknown"
    assert answer["tool"] is None
    assert answer["result"]["ok"] is False
    assert answer["result"]["error"] == "unsupported_question"
    assert tools.calls == []


def test_order_status_question_does_not_answer_with_store_state() -> None:
    tools = FakeTools()
    router = QuestionRouter(tools)

    answer = router.handle("3번 주문 어디쯤이에요?")

    assert answer["result"]["ok"] is False
    assert tools.calls == []


def test_handle_keeps_original_question_and_tool_result() -> None:
    tools = FakeTools()
    router = QuestionRouter(tools)

    answer = router.handle("얼마나 기다려야 해요?")

    assert answer["question"] == "얼마나 기다려야 해요?"
    assert answer["tool"] == "eta"
    assert answer["result"]["estimated_wait_minutes"] == 6
