from enum import StrEnum
import re
from typing import Any

from .tools import StoreTools


class QuestionType(StrEnum):
    MENU = "menu"
    STATE = "state"
    ETA = "eta"
    POLICY = "policy"
    ORDER = "order"
    UNKNOWN = "unknown"


KEYWORDS: dict[QuestionType, tuple[str, ...]] = {
    QuestionType.ORDER: (
        "주문상태",
        "주문어디",
        "내주문",
        "주문번호",
        "주문언제",
        "주문나와",
        "주문됐",
        "주문준비",
        "픽업",
        "order-",
    ),
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
        "판매",
        "파나요",
        "팔아",
        "있나요",
        "주문할수있",
    ),
    QuestionType.STATE: (
        "인원",
        "혼잡",
        "붐비",
        "사람",
        "자리",
        "몇명",
        "대기인원",
        "줄서",
    ),
    QuestionType.POLICY: (
        # 영업시간 · 라스트오더
        "영업",
        "몇시",
        "오픈",
        "마감",
        "닫아",
        "여나요",
        "라스트오더",
        "마지막주문",
        # 주차
        "주차",
        # 포장 · 매장 섭취
        "포장",
        "테이크아웃",
        "픽업",
        "매장섭취",
        # 환불
        "환불",
        "취소",
        "잘못주문",
        # 반려동물
        "반려동물",
        "애완동물",
        "강아지",
        "고양이",
        "안내견",
        # 와이파이
        "와이파이",
        "인터넷",
        "비밀번호",
        # 예약
        "예약",
        "단체",
        # 알레르기 · 우유 변경
        "알레르기",
        "견과류",
        "대두",
        "오트밀",
        "저당우유",
        "무가당",
        "우유변경",
        # 키오스크
        "키오스크",
        # 케어키즈존 · 유아 편의
        "케어키즈존",
        "어린이",
        "아이랑",
        "아동",
        "유아",
        "아기의자",
        "유모차",
        # 1인 1음료
        "1인1음료",
        "인당",
        "한명당",
        "몇명이서",
        # 매장 비품
        "휴지",
        "티슈",
        "화장지",
        "빨대",
        "셀프바",
        # 매장 이용시간
        "이용시간",
        "이용제한",
        "오래앉",
        "앉아있",
        # 흡연
        "흡연",
        "금연",
        "담배",
        # 화장실
        "화장실",
        "세면대",
        # 분실물
        "분실",
        "두고간",
        "잃어버",
        # 외부음식
        "외부음식",
        "음식반입",
        "가져가서먹",
        # 현금영수증
        "영수증",
        "소득공제",
        # 기프트 카드
        "기프트카드",
        "선불권",
        "매장카드",
        # 테라스
        "테라스",
        "야외",
        # 결제 수단
        "결제수단",
        "카드결제",
        "간편결제",
        "삼성페이",
        "카카오페이",
        "지역화폐",
        # 콘센트
        "콘센트",
        "충전",
        "노트북",
    ),
}

PRIORITY: tuple[QuestionType, ...] = (
    QuestionType.ORDER,
    QuestionType.ETA,
    QuestionType.POLICY,
    QuestionType.STATE,
    QuestionType.MENU,
)

POLICY_PENDING_MESSAGE = (
    "정책 질문은 RAG 연결 후 답변할 수 있습니다. 지금은 정책 원문을 그대로 전달합니다."
)

UNKNOWN_MESSAGE = "매장 상태, 대기시간, 메뉴, 정책 외의 질문은 아직 답변할 수 없습니다."


def _normalize(question: str) -> str:
    return "".join(question.split()).lower()


ORDER_ID_MISSING_MESSAGE = "주문번호를 알려주시면 상태를 확인해 드리겠습니다."


def extract_order_id(question: str) -> str | None:
    """질문에서 주문번호를 뽑는다. 'order-001' 형태를 우선 찾고,
    없으면 '3번'처럼 숫자만 있는 경우 order-00N으로 만든다.
    형식이 팀에서 확정되면 이 규칙만 바꾸면 된다."""
    text = _normalize(question)
    match = re.search(r"order-?(\d+)", text)
    if match:
        return f"order-{int(match.group(1)):03d}"
    match = re.search(r"(\d+)번", text)
    if match:
        return f"order-{int(match.group(1)):03d}"
    return None


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
        if question_type is QuestionType.ORDER:
            order_id = extract_order_id(question)
            if order_id is None:
                return {
                    "tool": "order",
                    "result": {
                        "ok": False,
                        "error": "order_id_missing",
                        "message": ORDER_ID_MISSING_MESSAGE,
                    },
                }
            return {"tool": "order", "result": self._tools.get_order_status(order_id)}
        if question_type is QuestionType.POLICY:
            return {
                "tool": "policy",
                "pending": "rag",
                "note": POLICY_PENDING_MESSAGE,
                "result": self._tools.get_policies(store_id),
            }
        return {
            "tool": None,
            "result": {
                "ok": False,
                "error": "unsupported_question",
                "message": UNKNOWN_MESSAGE,
            },
        }
