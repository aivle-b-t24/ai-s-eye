from typing import Any

import pytest

from aicc.router import QuestionRouter, QuestionType, classify, extract_order_id
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

    def get_policies(
        self,
        store_id: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append("policies")
        self.policy_query = query
        return {"ok": True, "policies": []}

    def get_order_status(self, order_id: str) -> dict[str, Any]:
        self.calls.append(f"order:{order_id}")
        return {"ok": True, "order_id": order_id, "status": "received"}


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
    ("question", "expected_calls"),
    [
        ("아메리카노 얼마예요?", ["menus"]),
        # 현황은 사이트 값(대기 주문·예상 대기시간)과 맞추려 state 뒤에 eta도 부른다.
        ("지금 몇 명 있나요?", ["state", "eta"]),
        ("얼마나 기다려야 해요?", ["eta"]),
        ("주차 되나요?", ["policies"]),
    ],
)
def test_router_calls_matching_tool(question: str, expected_calls: list[str]) -> None:
    tools = FakeTools()
    router = QuestionRouter(tools)

    router.handle(question)

    assert tools.calls == expected_calls


def test_menu_question_does_not_call_other_tools() -> None:
    tools = FakeTools()
    router = QuestionRouter(tools)

    router.handle("품절된 메뉴 알려주세요")

    assert tools.calls == ["menus"]


def test_policy_question_passes_query_for_rag() -> None:
    """정책 질문은 고객 질문을 query로 넘겨 관련 정책만 검색(RAG)한다."""
    tools = FakeTools()
    router = QuestionRouter(tools)

    answer = router.handle("영업시간이 어떻게 되나요?")

    assert answer["question_type"] == "policy"
    assert answer["tool"] == "policy"
    assert tools.calls == ["policies"]
    assert tools.policy_query == "영업시간이 어떻게 되나요?"  # 질문이 RAG 검색어로 전달됨
    # 옛 'pending: rag' 표시는 RAG 도입 후 없어졌다.
    assert "pending" not in answer


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

    # 주문 질문은 매장 상태(state)가 아니라 주문 Tool로 가야 한다.
    assert answer["tool"] == "order"
    assert tools.calls == ["order:order-003"]
    assert "state" not in tools.calls


def test_handle_keeps_original_question_and_tool_result() -> None:
    tools = FakeTools()
    router = QuestionRouter(tools)

    answer = router.handle("얼마나 기다려야 해요?")

    assert answer["question"] == "얼마나 기다려야 해요?"
    assert answer["tool"] == "eta"
    assert answer["result"]["estimated_wait_minutes"] == 6


@pytest.mark.parametrize(
    "question",
    [
        "order-001 주문 상태 알려줘",
        "내 주문 어디쯤이에요?",
        "주문 언제 나와요?",
        "3번 주문 준비됐어요?",
        "주문번호 5번 상태 확인해줘",
    ],
)
def test_order_questions_classified_as_order(question: str) -> None:
    assert classify(question) == QuestionType.ORDER


@pytest.mark.parametrize(
    "question",
    [
        "얼마나 기다려야 해요?",
        "아메리카노 얼마예요?",
        "지금 사람 많나요?",
        "주차 되나요?",
    ],
)
def test_non_order_questions_not_classified_as_order(question: str) -> None:
    assert classify(question) != QuestionType.ORDER


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("order-001 상태", "order-001"),
        ("order-42 어디쯤", "order-042"),
        ("3번 주문 준비됐어요?", "order-003"),
        ("주문 언제 나와요?", None),
        ("내 주문 어디쯤이에요?", None),
    ],
)
def test_extract_order_id(question: str, expected: str | None) -> None:
    assert extract_order_id(question) == expected


def test_router_calls_order_tool_with_extracted_id() -> None:
    tools = FakeTools()
    router = QuestionRouter(tools)

    answer = router.handle("order-001 주문 상태 알려줘")

    assert answer["tool"] == "order"
    assert tools.calls == ["order:order-001"]
    assert answer["result"]["ok"] is True


def test_router_asks_for_order_id_when_missing() -> None:
    tools = FakeTools()
    router = QuestionRouter(tools)

    answer = router.handle("내 주문 언제 나와요?")

    assert answer["tool"] == "order"
    assert answer["result"]["ok"] is False
    assert answer["result"]["error"] == "order_id_missing"
    assert tools.calls == []
