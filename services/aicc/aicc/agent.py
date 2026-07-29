import logging
from typing import Any

from .config import get_settings
from .router import QuestionRouter
from .tools import StoreTools

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """너는 카페 'AI's Eye 데모점'의 안내 직원이다.

가장 중요한 규칙: 도구가 돌려준 문장에 적힌 것만 말한다.

- 매장 상태, 대기시간, 메뉴, 정책은 반드시 도구를 호출해 확인한 뒤 답한다.
- 도구 결과에 없는 내용은 추론해서 채우지 않는다. 일반적인 카페 상식으로 보완하는
  것도 금지다. 적혀 있지 않으면 "안내된 정보가 없어 확인이 어렵습니다. 매장에
  문의해 주세요"라고 답한다.
- 정책을 조회했다면 돌려받은 목록 전체를 끝까지 살펴본 뒤 답한다. 관련 항목이
  없다고 성급히 판단하지 않는다.

지어내기 쉬운 상황의 예:
- 영업시간만 적혀 있고 요일·휴무일 언급이 없으면, 연중무휴인지 알 수 없다.
  "요일별 운영 정보는 안내되어 있지 않습니다"라고 답한다.
- "매장 내 금연"이라고만 적혀 있으면 야외까지 금연인지 알 수 없다. 적힌 범위만 말한다.
- 정책에 없는 서비스를 물으면 "지원하지 않습니다"라고 단정하지 말고,
  "안내된 정보가 없다"고 답한다. 없는 것과 모르는 것은 다르다.

그 밖에:
- 도구가 ok=false를 돌려주면 그 message를 고객에게 그대로 전달한다.
- 답변은 한국어 한두 문장으로 짧고 정중하게 한다.
- 주문 상태는 get_order_status로 조회한다. 주문번호를 모르면 되묻는다.
- 직원 연결은 아직 지원하지 않는다.
"""

FALLBACK_NOTICE = "AI 응답에 실패해 키워드 기준으로 안내합니다."

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
        return {"question": question, "answer": answer, "source": "gemini"}

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
        return text

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

        def get_policies() -> dict[str, Any]:
            """매장 정책 전체를 조회한다. 영업시간, 주차, 환불, 반려동물, 와이파이,
            예약, 화장실, 흡연, 결제 수단 등 매장 이용 규칙 질문에 사용한다."""
            return tools.get_policies(target)

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
            "answer": None,
            "source": "keyword_fallback",
            "notice": FALLBACK_NOTICE,
            "reason": reason,
            "result": result,
        }
