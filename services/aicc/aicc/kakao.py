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

from .store_directory import StoreDirectory, StoreEntry


class KakaoUser(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # 채널 안에서 손님을 구분하는 키(botUserKey). 유저별 선택 매장을 기억하는 데 쓴다.
    id: str | None = None

    @field_validator("id", mode="before")
    @classmethod
    def _coerce_id(cls, value: Any) -> str | None:
        if value is None:
            return None
        return str(value)


class KakaoUserRequest(BaseModel):
    # 카카오는 필드를 계속 늘리므로, 우리가 쓰는 것만 받고 나머지는 무시한다.
    model_config = ConfigDict(extra="ignore")

    utterance: str = ""
    user: KakaoUser = Field(default_factory=KakaoUser)
    # 오픈빌더에서 'AI 챗봇 콜백'을 켜면 카카오가 넘겨준다. 이 URL로 나중에 답을 POST하면
    # 5초 제한을 넘겨도(느린 LLM 응답) 손님에게 답이 전달된다.
    callbackUrl: str | None = None

    @field_validator("utterance", mode="before")
    @classmethod
    def _coerce_utterance(cls, value: Any) -> str:
        # utterance가 null이거나 문자열이 아니어도(카카오 샘플엔 null 필드가 많다)
        # 검증을 터뜨려 422를 내지 않는다. null은 빈 발화로 본다.
        if value is None:
            return ""
        return value if isinstance(value, str) else str(value)

    @field_validator("callbackUrl", mode="before")
    @classmethod
    def _coerce_callback_url(cls, value: Any) -> str | None:
        if not value:
            return None
        return str(value)

    @field_validator("user", mode="before")
    @classmethod
    def _coerce_user(cls, value: Any) -> Any:
        # user가 null로 와도 빈 유저로 다뤄 422를 피한다.
        return {} if value is None else value


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


def extract_user_id(payload: KakaoSkillPayload) -> str | None:
    """채널 안 손님 식별자. 유저별 선택 매장을 기억하는 세션 키로 쓴다."""
    return payload.userRequest.user.id or None


def extract_callback_url(payload: KakaoSkillPayload) -> str | None:
    """카카오 콜백 URL(있으면). 느린 답변을 나중에 이 URL로 POST한다."""
    return payload.userRequest.callbackUrl or None


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


def store_id_override(payload: KakaoSkillPayload) -> str | None:
    """봇 설정/링크가 넘겨준 매장(있으면). QR·딥링크로 특정 매장 대화를 여는 방식(A안).

    카카오 오픈빌더 봇 링크의 extra로 넣으면 action.clientExtra로 도착한다.
    clientExtra > params > detailParams 순으로 본다. 없으면 None.
    """
    action = payload.action
    for source in (action.clientExtra, action.params, action.detailParams):
        picked = _param_value(source.get("store_id"))
        if picked:
            return picked
    return None


def resolve_store_id(payload: KakaoSkillPayload, default_store_id: str) -> str:
    """override가 있으면 그 매장, 없으면 기본 매장(하위 호환용)."""
    return store_id_override(payload) or default_store_id


def build_skill_response(
    text: str,
    quick_replies: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """말풍선 하나(simpleText)로 이루어진 카카오 스킬 응답 2.0을 만든다."""
    template: dict[str, Any] = {"outputs": [{"simpleText": {"text": text}}]}
    if quick_replies:
        template["quickReplies"] = quick_replies
    return {"version": "2.0", "template": template}


# 답변이 5초를 넘길 수 있어서(느린 LLM), 콜백으로 "먼저 이 문구를 띄우고 나중에 진짜 답"을 보낸다.
CALLBACK_WAIT_TEXT = "확인하고 있어요! 잠시만 기다려 주세요 🙂"


def build_callback_ack(text: str = CALLBACK_WAIT_TEXT) -> dict[str, Any]:
    """콜백을 쓰겠다는 즉시 응답. 카카오가 이걸 받으면 실제 답을 콜백까지 기다린다(최대 ~1분)."""
    return {"version": "2.0", "useCallback": True, "data": {"text": text}}


# 손님이 누르면 그 문장이 그대로 질문으로 다시 들어온다(→ StoreAgent가 처리).
def _quick_reply(label: str, message_text: str) -> dict[str, str]:
    return {"label": label, "action": "message", "messageText": message_text}


DEFAULT_QUICK_REPLIES: list[dict[str, str]] = [
    # 라벨(버튼 글자)은 짧게, messageText(실제 보내는 질문)는 자연스러운 문장으로.
    _quick_reply("사람 많나요?", "지금 사람 많나요?"),
    _quick_reply("얼마나 기다려요?", "지금 가면 얼마나 기다려야 하나요?"),
    _quick_reply("메뉴", "메뉴 알려주세요"),
    _quick_reply("영업시간", "영업시간 알려주세요"),
]

GREETING_TEXT = (
    "안녕하세요! 매장 혼잡도·대기시간·메뉴·영업시간을 안내해 드려요. "
    "무엇이 궁금하세요?"
)
ERROR_TEXT = "지금은 안내가 어려워요. 잠시 후 다시 시도해 주세요."

# --- 멀티 매장(공용 채널) ---

# 카카오 퀵리플라이는 최대 10개까지만 노출된다.
MAX_STORE_QUICK_REPLIES = 10

PICK_STORE_TEXT = "어느 매장을 도와드릴까요? 아래에서 선택해 주세요."

# 채널 첫 진입 때 보여줄 인삿말 + 매장 선택 안내(선택 버튼과 함께 나간다).
WELCOME_TEXT = (
    "안녕하세요! 😊 매장 혼잡도·대기·메뉴·영업시간을 안내해 드려요.\n"
    "먼저 어느 매장이 궁금하신지 아래에서 골라주세요!"
)

CHANGE_STORE_LABEL = "매장 변경"
CHANGE_STORE_QUICK_REPLY = _quick_reply(CHANGE_STORE_LABEL, CHANGE_STORE_LABEL)

_CHANGE_STORE_TRIGGERS = (
    "매장변경",
    "매장바꿔",
    "매장바꾸",
    "다른매장",
    "매장선택",
    "매장다시",
)


def is_change_store(utterance: str) -> bool:
    """'매장 변경/다른 매장'처럼 매장을 다시 고르려는 발화인지."""
    norm = "".join(utterance.split())
    return any(trigger in norm for trigger in _CHANGE_STORE_TRIGGERS)


def store_quick_replies(entries: list[StoreEntry]) -> list[dict[str, str]]:
    """매장 목록을 선택 버튼으로. 누르면 그 매장 이름이 발화로 다시 들어온다."""
    return [
        _quick_reply(entry.name, entry.name)
        for entry in entries[:MAX_STORE_QUICK_REPLIES]
    ]


def answer_quick_replies(directory: StoreDirectory | None) -> list[dict[str, str]]:
    """답변에 붙일 퀵리플라이. 매장이 여러 개면 '매장 변경'을 덧붙인다."""
    replies = list(DEFAULT_QUICK_REPLIES)
    if directory is not None and directory.has_multiple():
        replies.append(CHANGE_STORE_QUICK_REPLY)
    return replies


def store_selected_text(store_name: str) -> str:
    return f"‘{store_name}’으로 안내해 드릴게요. 무엇이 궁금하세요?"


# 리스트카드는 최대 5개 항목. 그 이상이면 선택 버튼(퀵리플라이)으로 물러난다.
MAX_LIST_CARD_ITEMS = 5
STORE_PICK_HEADER = "어느 매장이 궁금하세요? 🏪"
WELCOME_INTRO = "안녕하세요! 😊 매장 혼잡도·대기·메뉴·영업시간을 안내해 드려요."


def build_store_picker(entries: list[StoreEntry], *, greeting: bool = False) -> dict[str, Any]:
    """매장 선택을 보기 좋게 만든다. 5개 이하면 리스트카드, 초과면 텍스트+선택버튼으로 물러난다.

    greeting=True(첫 진입)면 인삿말 말풍선을 카드 앞에 붙인다.
    """
    if entries and len(entries) <= MAX_LIST_CARD_ITEMS:
        outputs: list[dict[str, Any]] = []
        if greeting:
            outputs.append({"simpleText": {"text": WELCOME_INTRO}})
        outputs.append(
            {
                "listCard": {
                    "header": {"title": STORE_PICK_HEADER},
                    "items": [
                        {"title": entry.name, "action": "message", "messageText": entry.name}
                        for entry in entries
                    ],
                }
            }
        )
        return {"version": "2.0", "template": {"outputs": outputs}}
    # 6개 이상(또는 비어있음): 리스트카드 한도 초과 → 텍스트 + 선택 버튼
    text = f"{WELCOME_INTRO}\n{PICK_STORE_TEXT}" if greeting else PICK_STORE_TEXT
    return build_skill_response(text, store_quick_replies(entries))


# 답변 뒤에 붙는 '무엇이 궁금하세요?' 액션 메뉴(리스트카드). 라벨=버튼, messageText=실제 질문.
ACTION_MENU_HEADER = "무엇이 궁금하세요?"
_ACTION_MENU_ITEMS: list[tuple[str, str]] = [
    ("지금 붐비나요?", "지금 사람 많나요?"),
    ("얼마나 기다려요?", "지금 가면 얼마나 기다려야 하나요?"),
    ("메뉴·가격", "메뉴 알려주세요"),
    ("영업시간", "영업시간 알려주세요"),
]


def action_menu_output(
    directory: StoreDirectory | None,
    header: str = ACTION_MENU_HEADER,
) -> dict[str, Any]:
    """'무엇이 궁금하세요?' 리스트카드 한 장(출력 요소). 매장 여럿이면 '매장 변경' 추가."""
    items = [
        {"title": label, "action": "message", "messageText": message}
        for label, message in _ACTION_MENU_ITEMS
    ]
    if directory is not None and directory.has_multiple():
        items.append(
            {"title": CHANGE_STORE_LABEL, "action": "message", "messageText": CHANGE_STORE_LABEL}
        )
    return {"listCard": {"header": {"title": header}, "items": items[:MAX_LIST_CARD_ITEMS]}}


def build_action_menu(
    directory: StoreDirectory | None,
    header: str = ACTION_MENU_HEADER,
) -> dict[str, Any]:
    """액션 메뉴 리스트카드만 있는 응답(매장 선택 직후 등)."""
    return {"version": "2.0", "template": {"outputs": [action_menu_output(directory, header)]}}


def build_answer(text: str, directory: StoreDirectory | None) -> dict[str, Any]:
    """답변 말풍선 + 액션 메뉴 리스트카드."""
    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {"simpleText": {"text": text}},
                action_menu_output(directory),
            ]
        },
    }
