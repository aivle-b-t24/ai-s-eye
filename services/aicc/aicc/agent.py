import logging
import re
from typing import Any

from .config import get_settings
from .router import QuestionRouter, QuestionType, classify
from .tools import StoreTools

logger = logging.getLogger(__name__)

# 줄 맨 앞의 마크다운 불릿(*, -)을 잡는다. 뒤 공백까지 포함해 '• '로 바꾼다.
_MD_BULLET = re.compile(r"^([ \t]*)[*\-]\s+", re.MULTILINE)


def _tidy_markdown(text: str) -> str:
    """화면 말풍선은 마크다운을 렌더링하지 않으므로(기호가 그대로 보인다),
    모델이 섞어 쓴 마크다운 기호를 사람이 읽기 좋은 형태로 정리한다.

    - 줄 앞 불릿 '*'/'-' → '• '
    - 굵게 표시 '**...**' → 기호 제거(강조는 문장으로만)
    """
    text = _MD_BULLET.sub(r"\1• ", text)
    text = text.replace("**", "")
    return text


SYSTEM_PROMPT = """너는 카페 매장의 안내 직원이다.

가장 중요한 규칙: 도구가 돌려준 문장에 적힌 것만 말한다.

- 매장 상태, 대기시간, 메뉴, 정책은 반드시 도구를 호출해 확인한 뒤 답한다.
- 도구 결과에 없는 내용은 추론해서 채우지 않는다. 일반적인 카페 상식으로 보완하는
  것도 금지다. 적혀 있지 않으면 "안내된 정보가 없어 확인이 어렵습니다. 매장에
  문의해 주세요"라고 답한다.
- 물어본 것만 답한다. 묻지 않은 정보는 덧붙이지 않는다. 메뉴 이름·가격을 물으면 가격만
  안내하고, 품절 여부는 본문에도 맨 끝 ⚠️ 참고에도 넣지 않는다. 품절·재고는 손님이 그것을
  직접 물었을 때만, 그 답에서만 다룬다.
- 정책을 조회했다면 돌려받은 목록 전체를 끝까지 살펴본 뒤 답한다. 관련 항목이
  없다고 성급히 판단하지 않는다. 단, '살펴보는 것'은 전체지만 '답하는 것'은 관련 항목만이다.
- 정책 답변은 질문과 직접 관련된 항목만 골라 한두 문장으로 말한다. 손님이 하나를
  물으면 그 항목만 답하고, 관련 없는 다른 정책은 덧붙여 나열하지 않는다.
- "정책 다 알려줘 / 무슨 규칙 있어?"처럼 포괄적으로 물으면, 모든 정책을 길게 나열하지 않는다.
  대신 대표 항목 몇 개(예: 영업시간·주차·와이파이)만 짧게 들고 "어떤 점이 궁금하신가요?"라고
  되물어 범위를 좁힌다.

지어내기 쉬운 상황의 예:
- 영업시간만 적혀 있고 요일·휴무일 언급이 없으면, 연중무휴인지 알 수 없다.
  "요일별 운영 정보는 안내되어 있지 않습니다"라고 답한다.
- "매장 내 금연"이라고만 적혀 있으면 야외까지 금연인지 알 수 없다. 적힌 범위만 말한다.
- 정책에 없는 서비스를 물으면 "지원하지 않습니다"라고 단정하지 말고,
  "안내된 정보가 없다"고 답한다. 없는 것과 모르는 것은 다르다.

그 밖에:
- 도구가 ok=false를 돌려주면 그 message를 고객에게 그대로 전달한다.
- 답변은 반드시 한국어로만, 짧고 정중하게 한다. 영어 번역이나 영어 문장을 덧붙이지 않는다.
- 주문 상태는 get_order_status로 조회한다. 주문번호를 모르면 되묻는다.
- "붐비는지/혼잡/얼마나 기다려" 같은 혼잡도 질문에는 get_store_state와 get_wait_time을 함께
  조회해, 매장 인원·대기 인원·예상 대기시간을 "• " 불릿으로 함께 안내한다.
- 직원 연결은 아직 지원하지 않는다.

답변 형식 (읽기 좋게):
- 핵심 답을 먼저 한 문장으로 말한다.
- 나열할 항목이 둘 이상이면 각 줄을 "• "로 시작하는 불릿으로 쓴다(한 항목당 한 줄).
- 주의·한계가 있으면 맨 끝에 "⚠️ 참고 — ..." 한 줄로 덧붙인다. 없으면 넣지 않는다.
  단, 품절·재고 같은 개별 항목 상태는 ⚠️ 참고에 넣지 않는다(품절은 품절을 물었을 때만 답한다).
- 항목/문단은 빈 줄로 구분해 답답하지 않게 한다.
- 굵게(**), 제목(#), 표 같은 마크다운 기호는 쓰지 않는다. 화면에 기호가 그대로 보이므로 금지.
  강조는 기호 없이 문장으로 한다. 이모지는 ⚠️ 정도만 절제해서 쓴다.
- 답이 짧으면(가격 하나, 대기시간 하나 등) 불릿 없이 한 문장으로 끝낸다. 억지로 늘리지 않는다.
- 이 형식으로 꾸미더라도 내용은 도구가 준 데이터만 쓴다(위 규칙 그대로). 형식 때문에 없는 항목을 만들지 않는다.
"""

FALLBACK_NOTICE = "AI 응답에 실패해 키워드 기준으로 안내합니다."

# '이어서 물어보세요'용 추천 질문. 종류별 대표 질문 하나씩 두고,
# 방금 물어본 종류는 빼서 같은 질문을 다시 권하는 어색함을 막는다. 모두 우리가 답할 수 있는 것.
# 화면(완태)에서 버튼으로 그려 누르면 그대로 재질문된다.
_TOPIC_QUESTION: dict[QuestionType, str] = {
    QuestionType.MENU: "메뉴 가격 알려줘",
    QuestionType.STATE: "지금 매장 붐벼?",
    QuestionType.ETA: "예상 대기시간 얼마야?",
    QuestionType.POLICY: "영업시간 언제까지야?",
}
_TOPIC_ORDER: tuple[QuestionType, ...] = (
    QuestionType.MENU,
    QuestionType.STATE,
    QuestionType.ETA,
    QuestionType.POLICY,
)


def suggest_questions(question: str, limit: int = 2) -> list[str]:
    """이어서 물어볼 추천 질문. 방금 물어본 종류는 빼고 다른 종류를 권한다."""
    asked = classify(question)
    picks = [q for t, q in ((t, _TOPIC_QUESTION[t]) for t in _TOPIC_ORDER) if t != asked]
    return picks[:limit]

# 무한루프 방지: 질문 하나에 도구를 이 횟수까지만 자동 호출한다.
# 우리 챗봇은 질문당 도구 1~2번이면 충분하므로 5로 제한한다(SDK 기본값은 10).
# 이 횟수를 넘으면 도구 호출을 멈춰서, 무한정 반복하며 토큰을 소진하는 것을 막는다.
MAX_TOOL_CALLS = 5


class GeminiUnavailableError(RuntimeError):
    """Gemini를 쓸 수 없을 때. 호출한 쪽이 키워드 분기로 넘어가면 된다."""


class StoreAgent:
    """Gemini에 Tool을 넘겨 고객 질문에 답한다.

    Gemini 호출이 실패하면 키워드 기반 QuestionRouter로 넘어간다. 무료 한도 초과나
    네트워크 오류로 대화가 멈추지 않도록 하기 위해서다.
    """

    def __init__(self, tools: StoreTools | None = None) -> None:
        self._tools = tools if tools is not None else StoreTools()
        self._router = QuestionRouter(self._tools)
        self._settings = get_settings()
        self._client = self._build_client()

    def _build_client(self) -> Any | None:
        """Vertex AI(사내 크레딧) 또는 API 키(무료 등급) 중 설정된 쪽으로 연결한다.

        AICC_VERTEX_PROJECT가 있으면 Vertex AI를 쓴다. gcloud 인증이 필요하지만
        Google Cloud 크레딧을 쓸 수 있다. 없으면 GOOGLE_API_KEY로 무료 등급에 붙는다.
        """
        try:
            from google import genai
        except ImportError:
            return None

        settings = self._settings
        if settings.use_vertex:
            try:
                return genai.Client(
                    vertexai=True,
                    project=settings.vertex_project,
                    location=settings.vertex_location,
                )
            except Exception:
                # 연결 실패해도 앱은 키워드 방식으로 넘어간다. 다만 원인은 로그로 남긴다.
                logger.warning("Vertex Gemini 클라이언트 생성 실패", exc_info=True)
                return None

        if not settings.gemini_api_key:
            return None
        return genai.Client(api_key=settings.gemini_api_key)

    def close(self) -> None:
        self._tools.close()

    def __enter__(self) -> "StoreAgent":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def ask(self, question: str, store_id: str | None = None) -> dict[str, Any]:
        try:
            answer = self._ask_gemini(question, store_id)
        except GeminiUnavailableError as exc:
            return self._fallback(question, store_id, str(exc))
        return {
            "question": question,
            "answer": answer,
            "source": "gemini",
            "suggestions": suggest_questions(question),
        }

    def _ask_gemini(self, question: str, store_id: str | None) -> str:
        if self._client is None:
            raise GeminiUnavailableError("Gemini 클라이언트를 만들지 못했습니다.")

        from google.genai import types

        try:
            response = self._client.models.generate_content(
                model=self._settings.gemini_model,
                contents=question,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    tools=self._tool_functions(store_id),
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        maximum_remote_calls=MAX_TOOL_CALLS,
                    ),
                ),
            )
        except Exception as exc:
            raise GeminiUnavailableError(f"{type(exc).__name__}: {exc}") from exc

        text = (response.text or "").strip()
        if not text:
            raise GeminiUnavailableError("Gemini가 빈 응답을 돌려줬습니다.")
        return _tidy_markdown(text)

    def _tool_functions(self, store_id: str | None) -> list[Any]:
        """Gemini에 넘길 함수 목록. 독스트링이 그대로 도구 설명이 된다."""
        tools = self._tools
        target = store_id

        def get_store_state() -> dict[str, Any]:
            """현재 매장의 인원 수와 대기 인원을 조회한다. 혼잡도 질문에 사용한다."""
            return tools.get_store_state(target)

        def get_wait_time() -> dict[str, Any]:
            """현재 예상 대기시간을 분 단위로 조회한다."""
            return tools.get_eta(target)

        def get_menus(menu_name: str | None = None) -> dict[str, Any]:
            """메뉴의 가격과 판매 여부를 조회한다.

            Args:
                menu_name: 특정 메뉴만 볼 때 그 이름. 생략하면 전체 메뉴를 돌려준다.
            """
            return tools.get_menus(target, menu_name)

        def get_policies(query: str) -> dict[str, Any]:
            """매장 정책을 조회한다. 영업시간, 주차, 환불, 반려동물, 와이파이,
            예약, 화장실, 흡연, 결제 수단 등 매장 이용 규칙 질문에 사용한다.

            Args:
                query: 고객이 알고 싶어하는 내용. 고객 질문을 그대로 넣으면 된다.
                    이 내용과 관련된 정책만 추려서 돌려준다. 예: "주차 되나요?"
            """
            return tools.get_policies(target, query)

        def get_order_status(order_id: str) -> dict[str, Any]:
            """주문번호로 현재 주문 상태(접수/제조중/준비완료 등)를 조회한다.
            '내 주문 언제 나와요?' 같은 주문 진행 질문에 사용한다.

            Args:
                order_id: 조회할 주문번호. 예: order-001. 고객이 '3번 주문'처럼
                    말하면 order-003 형태로 만들어 넘긴다. 번호를 모르면 호출하지
                    말고 고객에게 주문번호를 되묻는다.
            """
            return tools.get_order_status(order_id)

        return [
            get_store_state,
            get_wait_time,
            get_menus,
            get_policies,
            get_order_status,
        ]

    def _fallback(
        self,
        question: str,
        store_id: str | None,
        reason: str,
    ) -> dict[str, Any]:
        result = self._router.handle(question, store_id)
        return {
            "question": question,
            "answer": _fallback_answer(result),
            "source": "keyword_fallback",
            "notice": FALLBACK_NOTICE,
            "reason": reason,
            "result": result,
            "suggestions": suggest_questions(question),
        }


def _fallback_answer(routed: dict[str, Any]) -> str:
    """Gemini를 못 쓸 때, 키워드 분기 결과를 고객이 읽을 문장으로 바꾼다.

    Gemini가 죽어도 raw 데이터 대신 사람이 읽는 답을 주기 위한 것이다.
    """
    inner = routed.get("result")
    if not isinstance(inner, dict):
        return FALLBACK_NOTICE
    # 도구가 오류(ok=False)면 그 message는 이미 고객에게 보여줄 문장이다.
    if inner.get("ok") is False:
        return str(inner.get("message") or "요청을 처리하지 못했습니다.")

    tool = routed.get("tool")
    if tool == "state":
        return (
            f"현재 매장에 {inner.get('visible_person_count')}명이 있고, "
            f"대기 인원은 {inner.get('queue_count_estimate')}명입니다."
        )
    if tool == "eta":
        return f"예상 대기시간은 약 {inner.get('estimated_wait_minutes')}분입니다."
    if tool == "order":
        return str(inner.get("status_message") or "주문 상태를 확인했습니다.")
    if tool == "menu":
        if inner.get("message"):
            return str(inner["message"])
        menus = inner.get("menus") or []
        if not menus:
            return "해당 메뉴 정보를 찾지 못했습니다."
        lines = ["메뉴를 안내해 드릴게요.", ""]
        for m in menus[:5]:
            price = f"{m.get('price')}원" if m.get("price") is not None else "가격 미정"
            sold = " (품절)" if m.get("available") is False else ""
            lines.append(f"• {m.get('name')}: {price}{sold}")
        return "\n".join(lines)
    if tool == "policy":
        policies = inner.get("policies") or []
        if not policies:
            return "관련 정책 정보를 찾지 못했습니다."
        if len(policies) == 1:
            return str(policies[0].get("content") or "관련 정책 정보를 찾지 못했습니다.")
        lines = ["안내해 드릴게요.", ""]
        for p in policies[:3]:
            lines.append(f"• {p.get('title')}: {p.get('content')}")
        return "\n".join(lines)
    return FALLBACK_NOTICE
