from enum import StrEnum
from typing import Any

from .tools import StoreTools


class QuestionType(StrEnum):
    MENU = "menu"
    STATE = "state"
    ETA = "eta"
    POLICY = "policy"
    UNKNOWN = "unknown"


KEYWORDS: dict[QuestionType, tuple[str, ...]] = {
    QuestionType.ETA: (
        "대기시간",
        "얼마나기다",
        "얼마나걸",
        "몇분",
        "언제나와",
        "언제받",
        "오래걸리",
    ),
    QuestionType.MENU: (
        "메뉴",
        "가격",
        "얼마",
        "품절",
        "솔드아웃",
        "재고",
        "파나요",
        "팔아",
        "있나요",
        "주문할수있",
    ),
    QuestionType.STATE: (
        "인원",
        "혼잡",
        "붐비",
        "사람많",
        "자리",
        "몇명",
        "대기인원",
        "줄서",
    ),
    QuestionType.POLICY: (
        "영업시간",
        "몇시",
        "오픈",
        "마감",
        "닫",
        "여나요",
        "주차",
        "환불",
        "취소",
        "포장",
        "테이크아웃",
        "반려동물",
        "강아지",
        "안내견",
    ),
}

PRIORITY: tuple[QuestionType, ...] = (
    QuestionType.ETA,
    QuestionType.POLICY,
    QuestionType.STATE,
    QuestionType.MENU,
)

POLICY_PENDING_MESSAGE = (
    "정책 질문은 RAG 연결 후 답변할 수 있습니다. 지금은 정책 원문을 그대로 전달합니다."
)

UNKNOWN_MESSAGE = "질문 유형을 알지 못해 매장 상태와 대기시간을 안내합니다."


def _normalize(question: str) -> str:
    return "".join(question.split()).lower()


def classify(question: str) -> QuestionType:
    """질문을 Tool 종류로 나눈다. LLM 없이 키워드로만 판단한다."""

    text = _normalize(question)
    for question_type in PRIORITY:
        if any(keyword in text for keyword in KEYWORDS[question_type]):
            return question_type
    return QuestionType.UNKNOWN


class QuestionRouter:
    """질문 유형을 보고 알맞은 Tool을 호출한다.

    정책 질문은 추후 RAG가 맡을 자리다. 그전까지는 정책 Tool의 원문을 그대로 돌려준다.
    """

    def __init__(self, tools: StoreTools | None = None) -> None:
        self._tools = tools if tools is not None else StoreTools()

    def close(self) -> None:
        self._tools.close()

    def __enter__(self) -> "QuestionRouter":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def handle(self, question: str, store_id: str | None = None) -> dict[str, Any]:
        question_type = classify(question)
        result = self._call(question_type, question, store_id)
        return {"question": question, "question_type": question_type.value, **result}

    def _call(
        self,
        question_type: QuestionType,
        question: str,
        store_id: str | None,
    ) -> dict[str, Any]:
        if question_type is QuestionType.MENU:
            return {"tool": "menu", "result": self._tools.get_menus(store_id)}
        if question_type is QuestionType.STATE:
            return {"tool": "state", "result": self._tools.get_store_state(store_id)}
        if question_type is QuestionType.ETA:
            return {"tool": "eta", "result": self._tools.get_eta(store_id)}
        if question_type is QuestionType.POLICY:
            return {
                "tool": "policy",
                "pending": "rag",
                "note": POLICY_PENDING_MESSAGE,
                "result": self._tools.get_policies(store_id),
            }
        return {
            "tool": "state",
            "note": UNKNOWN_MESSAGE,
            "result": self._tools.get_store_state(store_id),
        }
