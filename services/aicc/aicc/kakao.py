"""카카오톡 i 오픈빌더 스킬 웹훅 어댑터.

손님이 카카오톡 채널에 보낸 질문을 기존 챗봇 두뇌(StoreAgent)에 그대로 넘기고,
그 답을 카카오 스킬 응답 형식(version 2.0)으로 감싼다. 여기서는 '형식 변환'만 하고
질문 이해·조회·답변 생성은 전부 StoreAgent가 맡는다.

카카오 스킬 서버 규약(요지):
- 요청: JSON. 실제 질문은 userRequest.utterance, 봇 설정값은 action.clientExtra/params에 온다.
- 응답: {"version": "2.0", "template": {"outputs": [...], "quickReplies": [...]}}
  outputs의 simpleText.text가 손님에게 보이는 말풍선이다.
- 오류라도 200 + 스킬 형식으로 답해야 카카오가 사람에게 문장을 보여준다. 비-200이면
  '오류가 발생했습니다' 시스템 메시지만 떠서 안내가 사라진다. 그래서 호출부는 어떤
  경우에도 build_skill_response로 감싼 200을 돌려준다.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class KakaoUserRequest(BaseModel):
    # 카카오는 필드를 계속 늘리므로, 우리가 쓰는 것만 받고 나머지는 무시한다.
    model_config = ConfigDict(extra="ignore")

    utterance: str = ""

    @field_validator("utterance", mode="before")
    @classmethod
    def _coerce_utterance(cls, value: Any) -> str:
        # utterance가 null이거나 문자열이 아니어도(카카오 샘플엔 null 필드가 많다)
        # 검증을 터뜨려 422를 내지 않는다. null은 빈 발화로 본다.
        if value is None:
            return ""
        return value if isinstance(value, str) else str(value)


class KakaoAction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    params: dict[str, Any] = Field(default_factory=dict)
    detailParams: dict[str, Any] = Field(default_factory=dict)
    clientExtra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("params", "detailParams", "clientExtra", mode="before")
    @classmethod
    def _none_to_dict(cls, value: Any) -> Any:
        # 이 필드들이 null로 와도 빈 dict로 다뤄 422를 피한다.
        return {} if value is None else value


class KakaoSkillPayload(BaseModel):
    """카카오 스킬 요청 본문. 필요한 두 덩어리(userRequest·action)만 본다."""

    model_config = ConfigDict(extra="ignore")

    userRequest: KakaoUserRequest = Field(default_factory=KakaoUserRequest)
    action: KakaoAction = Field(default_factory=KakaoAction)


def coerce_payload(body: Any) -> KakaoSkillPayload:
    """카카오가 무엇을 보내도 예외 없이 최대한 살려 파싱한다.

    엔드포인트는 이 함수만 쓰고 요청을 Pydantic 모델 파라미터로 직접 받지 않는다.
    모델 파라미터로 받으면 검증 실패가 FastAPI 단계에서 422로 튀어(카카오는 이걸
    '올바르지 않은 스킬 서버 응답'으로 거부한다) '어떤 경우에도 200' 규약이 깨진다.
    """
    if not isinstance(body, dict):
        return KakaoSkillPayload()
    try:
        return KakaoSkillPayload.model_validate(body)
    except ValidationError:
        # 최악의 경우에도 발화만이라도 건져 인사/안내로 이어지게 한다.
        utterance = ""
        user_request = body.get("userRequest")
        if isinstance(user_request, dict):
            raw = user_request.get("utterance")
            if raw not in (None, ""):
                utterance = str(raw)
        return KakaoSkillPayload(userRequest=KakaoUserRequest(utterance=utterance))


def extract_utterance(payload: KakaoSkillPayload) -> str:
    """손님이 실제로 친 말. 앞뒤 공백은 정리한다."""
    return (payload.userRequest.utterance or "").strip()


def _param_value(value: Any) -> str | None:
    """카카오 파라미터 값을 문자열로 꺼낸다.

    detailParams는 {"value": "...", "origin": "..."} 형태로, params/clientExtra는
    보통 평범한 문자열로 온다. 둘 다 다룬다."""
    if isinstance(value, dict):
        picked = value.get("value") or value.get("origin")
        return str(picked).strip() if picked else None
    if value in (None, ""):
        return None
    return str(value).strip()


def resolve_store_id(payload: KakaoSkillPayload, default_store_id: str) -> str:
    """이 대화가 어느 매장인지 정한다.

    채널 1개 = 매장 1개가 기본이라 default_store_id를 쓰되, 봇 설정에서 store_id를
    넘겨주면(멀티 매장 확장) 그걸 우선한다. clientExtra > params > detailParams 순.
    """
    action = payload.action
    for source in (action.clientExtra, action.params, action.detailParams):
        picked = _param_value(source.get("store_id"))
        if picked:
            return picked
    return default_store_id


def build_skill_response(
    text: str,
    quick_replies: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """말풍선 하나(simpleText)로 이루어진 카카오 스킬 응답 2.0을 만든다."""
    template: dict[str, Any] = {"outputs": [{"simpleText": {"text": text}}]}
    if quick_replies:
        template["quickReplies"] = quick_replies
    return {"version": "2.0", "template": template}


# 손님이 누르면 그 문장이 그대로 질문으로 다시 들어온다(→ StoreAgent가 처리).
def _quick_reply(label: str, message_text: str) -> dict[str, str]:
    return {"label": label, "action": "message", "messageText": message_text}


DEFAULT_QUICK_REPLIES: list[dict[str, str]] = [
    _quick_reply("혼잡도", "지금 붐비나요?"),
    _quick_reply("대기시간", "지금 가면 얼마나 기다려요?"),
    _quick_reply("메뉴", "메뉴 알려주세요"),
    _quick_reply("영업시간", "영업시간 알려주세요"),
]

GREETING_TEXT = (
    "안녕하세요! 매장 혼잡도·대기시간·메뉴·영업시간을 안내해 드려요. "
    "무엇이 궁금하세요?"
)
ERROR_TEXT = "지금은 안내가 어려워요. 잠시 후 다시 시도해 주세요."
