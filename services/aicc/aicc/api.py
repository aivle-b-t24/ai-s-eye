"""AICC 슈퍼바이저 인사이트 API.

기간을 받아 공통 API의 집계(GET /api/stores/summary)를 부르고,
그 결과를 Gemini로 분석해(generate_insights) 슈퍼바이저용 인사이트를 돌려준다.

오류는 원인별로 구분한다:
- 입력 형식 오류        → 422 (FastAPI 검증)
- 공통(집계) API 오류    → 502 store_api_error
- Gemini(분석) 오류      → 503 insights_unavailable
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

from .agent import StoreAgent
from .auth import ADMIN_ROLE, CurrentUser, get_current_user, require_admin
from .client import StoreApiClient
from .config import get_settings
from .errors import ToolError
from .franchise_insights import InsightsUnavailableError, generate_insights
from .kakao import (
    ERROR_TEXT,
    build_action_menu,
    build_answer,
    build_callback_ack,
    build_store_picker,
    coerce_payload,
    extract_callback_url,
    extract_user_id,
    extract_utterance,
    is_change_store,
    store_id_override,
)
from .session import SessionStore
from .store_directory import (
    directory_from_items,
    load_store_directory,
    parse_name_overlay,
)
from .scene_detection import (
    SceneImageRequest,
    SceneSuggestionResponse,
    SceneSuggestionUnavailableError,
    generate_scene_suggestion,
)
from .store_context import StoreContextProvider, build_sgis_client

logger = logging.getLogger(__name__)


class InsightsRequest(BaseModel):
    """분석 요청. 기간은 선택이며, 주면 시작<끝이어야 한다."""

    start_at: str | None = Field(default=None, description="집계 시작 시각(ISO8601)")
    end_at: str | None = Field(default=None, description="집계 끝 시각(ISO8601)")

    @model_validator(mode="after")
    def _check_order(self) -> "InsightsRequest":
        if self.start_at and self.end_at and self.start_at >= self.end_at:
            raise ValueError("start_at은 end_at보다 앞서야 합니다.")
        return self


class Insight(BaseModel):
    store_id: str
    insight_type: str | None = None
    severity: str | None = None
    summary: str | None = None
    probable_cause: str | None = Field(default=None, description="왜 그런지에 대한 추정(가설)")
    evidence: dict[str, Any] = Field(default_factory=dict)
    recommendation: str | None = None
    display_text: str | None = Field(default=None, description="관리자가 바로 읽는 문장")


class Comparison(BaseModel):
    summary: str | None = None
    recommendation: str | None = None
    display_text: str | None = Field(default=None, description="관리자가 바로 읽는 문장")


class InsightsResponse(BaseModel):
    insights: list[Insight]
    comparison: Comparison = Field(default_factory=Comparison)


class ChatTurn(BaseModel):
    """이전 대화 한 마디. role은 'user'(손님)/'model'(챗봇). 프론트의 'bot'도 허용한다."""

    role: str = Field(description="user 또는 model(=bot)")
    text: str = Field(max_length=500)


class ChatRequest(BaseModel):
    """챗봇 질문. question은 필수, 너무 긴 입력은 막는다(토큰 낭비 방지).

    history를 주면 멀티턴(대화 기억)으로 동작한다. 프론트가 최근 대화 몇 개를 실어 보내면
    챗봇이 맥락("그거·아까 그거")을 이어서 이해한다. 없으면 단일 질문으로 답한다.
    """

    question: str = Field(min_length=1, max_length=500, description="고객 질문")
    store_id: str | None = Field(default=None, description="매장 ID. 없으면 기본 매장")
    history: list[ChatTurn] = Field(
        default_factory=list, description="이전 대화(맥락 유지용). 최근 것만 보내면 됨"
    )

    @model_validator(mode="after")
    def _check_not_blank(self) -> "ChatRequest":
        # 공백만 있는 질문은 빈 질문과 같으므로 막는다.
        if not self.question.strip():
            raise ValueError("question은 공백만으로 이루어질 수 없습니다.")
        return self


class ChatResponse(BaseModel):
    question: str
    answer: str | None = None
    source: str  # "gemini" 또는 "keyword_fallback"
    suggestions: list[str] = Field(
        default_factory=list, description="이어서 물어볼 추천 질문(화면에서 버튼으로 표시)"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = StoreApiClient()
    app.state.agent = StoreAgent()
    # 상권 프로필(SGIS)은 앱 하나당 한 번만 만들어 매장별로 캐시한다(요청마다 재조회 방지).
    app.state.store_context = StoreContextProvider(build_sgis_client(get_settings()))
    try:
        yield
    finally:
        app.state.client.close()
        app.state.agent.close()


app = FastAPI(title="AICC Insights API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz", tags=["health"])
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/insights",
    response_model=InsightsResponse,
    tags=["insights"],
    dependencies=[Depends(require_admin)],
)
def create_insights(req: InsightsRequest) -> Any:
    """기간별 집계를 분석해 슈퍼바이저 인사이트를 생성한다."""
    # 1) 공통 API에서 집계 가져오기
    try:
        summary = app.state.client.get_store_summary(req.start_at, req.end_at)
    except ToolError as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": "store_api_error", "message": exc.message},
        ) from exc

    # 2) Gemini로 분석 (상권 프로필 포함). store_context가 없으면(예: 테스트) None → 내부 기본값.
    try:
        result = generate_insights(
            summary, context_provider=getattr(app.state, "store_context", None)
        )
    except InsightsUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": "insights_unavailable", "message": f"분석을 생성하지 못했습니다: {exc}"},
        ) from exc

    return result


@app.post("/chat", response_model=ChatResponse, tags=["chat"])
def create_chat(
    req: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
) -> Any:
    """고객 질문에 답한다.

    Gemini가 질문을 이해해 필요한 매장 정보를 조회하고 답변을 만든다.
    Gemini를 못 쓰면 키워드 방식으로 넘어가며, 어느 쪽이든 answer는 사람이 읽는 문장이다.
    """
    if (
        user.role != ADMIN_ROLE
        and req.store_id is not None
        and req.store_id != user.store_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="담당 매장에만 접근할 수 있습니다",
        )
    target_store_id = user.store_id if user.role != ADMIN_ROLE else req.store_id
    store = target_store_id or "-"
    logger.info("chat 질문 store=%s: %s", store, req.question)
    history = [{"role": t.role, "text": t.text} for t in req.history]
    try:
        result = app.state.agent.ask(req.question, target_store_id, history=history)
    except Exception as exc:
        # ask()는 대개 내부에서 오류를 흡수하지만, 예상 밖 예외가 새도 500으로 터지지 않게 막는다.
        logger.warning("chat 실패 store=%s: %s", store, exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail={"error": "chat_unavailable", "message": f"답변을 생성하지 못했습니다: {exc}"},
        ) from exc
    logger.info(
        "chat 답변 store=%s source=%s: %s",
        store,
        result.get("source"),
        result.get("answer"),
    )
    return result


def _verify_kakao_token(header_token: str | None, query_token: str | None) -> None:
    """스킬 웹훅 공유 토큰을 검사한다.

    AICC_KAKAO_SKILL_TOKEN이 설정돼 있으면 헤더(X-Kakao-Skill-Token)나 쿼리(?token=)
    중 하나가 일치해야 한다. 카카오는 요청에 서명을 붙이지 않으므로, 스킬 URL을 아는
    아무나 부르는 것을 막는 최소 장치다. 설정이 비어 있으면(개발) 검사를 건너뛴다.
    """
    expected = get_settings().kakao_skill_token
    if not expected:
        return
    if header_token != expected and query_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 스킬 토큰입니다.",
        )


def _get_session() -> SessionStore:
    """유저별 선택 매장 세션. lifespan 없이(테스트) 접근해도 자동 생성된다."""
    session = getattr(app.state, "session", None)
    if session is None:
        session = SessionStore(ttl_seconds=get_settings().session_ttl_seconds)
        app.state.session = session
    return session


# 매장 목록을 매 요청마다 백엔드에 묻지 않도록 잠깐 캐싱한다. 새 매장은 이 시간 안에 반영된다.
STORE_DIRECTORY_TTL_SECONDS = 60.0


def _build_store_directory():
    """공용 채널이 안내할 매장 목록을 만든다.

    매장 목록·이름은 백엔드 매장 마스터(`/internal/stores`)에서 실시간으로 가져와, 본사가
    매장을 등록하면 이름과 함께 선택지에 자동으로 들어온다. 백엔드가 이름을 주지 않는
    경우엔 `AICC_STORE_DIRECTORY` 이름 오버레이 → store_id 순으로 물러난다. 백엔드를 못
    읽으면(로컬 등) 설정값만으로 물러난다.
    """
    settings = get_settings()
    overlay = parse_name_overlay(settings.store_directory_raw)
    client = getattr(app.state, "client", None)
    if client is not None:
        try:
            body = client.list_stores()
            items = [item for item in (body.get("stores") or []) if isinstance(item, dict)]
            if items:
                return directory_from_items(items, overlay)
        except Exception:
            logger.warning("매장 목록 조회 실패 — 설정값으로 폴백", exc_info=True)
    return load_store_directory(settings.store_directory_raw)


def _get_store_directory():
    """공용 채널이 안내하는 매장 목록. 테스트가 명시 세팅했으면 그것을, 아니면 백엔드에서
    가져와 TTL 동안 캐싱한다."""
    override = getattr(app.state, "store_directory", None)
    if override is not None:
        return override
    cache = getattr(app.state, "_store_directory_cache", None)
    now = time.monotonic()
    if cache is not None and now - cache[1] <= STORE_DIRECTORY_TTL_SECONDS:
        return cache[0]
    directory = _build_store_directory()
    app.state._store_directory_cache = (directory, now)
    return directory


def _answer_text(utterance: str, store_id: str) -> str:
    """StoreAgent로 답 문장을 만든다(느릴 수 있음). 어떤 경우에도 문장을 돌려준다."""
    try:
        result = app.state.agent.ask(utterance, store_id)
        return (result.get("answer") or "").strip() or ERROR_TEXT
    except Exception as exc:
        logger.warning("kakao 답변 실패 store=%s: %s", store_id, exc, exc_info=True)
        return ERROR_TEXT


def _send_kakao_callback(
    callback_url: str,
    utterance: str,
    store_id: str,
    directory,
) -> None:
    """느린 답변을 만들어 카카오 콜백 URL로 보낸다(백그라운드에서 실행).

    5초 제한을 넘겨도 손님에게 답이 전달되도록, 즉시 useCallback을 준 뒤 여기서 실제
    답을 계산해 콜백으로 POST한다.
    """
    answer = _answer_text(utterance, store_id)
    body = build_answer(answer, directory)
    try:
        httpx.post(callback_url, json=body, timeout=15.0)
    except Exception as exc:
        logger.warning("kakao 콜백 전송 실패 store=%s: %s", store_id, exc, exc_info=True)


@app.post("/kakao/skill", tags=["kakao"])
async def kakao_skill(
    request: Request,
    background_tasks: BackgroundTasks,
    x_kakao_skill_token: str | None = Header(default=None),
    token: str | None = Query(default=None),
) -> Any:
    """카카오톡 채널의 손님 질문을 받아 스킬 응답(2.0)으로 답한다.

    공용 채널 하나로 여러 매장을 처리한다. 매장을 정하는 순서:
      1) QR·딥링크가 넘긴 store_id(clientExtra) — 있으면 그 매장으로 고정하고 기억(A안)
      2) 이 손님이 앞서 고른 매장(세션)
      3) 매장이 여러 개면 발화에서 선택을 읽거나, 없으면 선택 버튼을 보여줌(B안)
      4) 매장이 하나뿐/미설정이면 기본 매장

    질문 이해·조회·답변은 /chat과 같은 StoreAgent가 처리한다. 여기서는 카카오 형식
    변환·매장 라우팅과, 어떤 상황에도 200 스킬 응답을 주는 것만 담당한다(본문은
    관대하게 파싱해 422를 내지 않는다).
    """
    _verify_kakao_token(x_kakao_skill_token, token)

    try:
        body = await request.json()
    except Exception:
        body = None
    payload = coerce_payload(body)

    utterance = extract_utterance(payload)
    user_id = extract_user_id(payload)
    session = _get_session()
    directory = _get_store_directory()

    # 1) QR·딥링크가 매장을 지정했으면 그 매장으로 고정하고 기억(A안)
    override = store_id_override(payload)
    if override:
        session.set(user_id, override)

    # '매장 변경' 요청 → 기억 초기화하고 다시 선택받기
    if not override and utterance and is_change_store(utterance) and directory.has_multiple():
        session.clear(user_id)
        return build_store_picker(directory.list())

    store_id = override or session.get(user_id)

    # 2·3) 아직 매장 미정 + 매장이 여러 개
    if not store_id and directory.has_multiple():
        # 채널 첫 진입(빈 발화) → 인삿말 + 매장 선택 카드
        if not utterance:
            return build_store_picker(directory.list(), greeting=True)
        selected = directory.resolve(utterance)
        if selected:
            session.set(user_id, selected)
            # 매장 선택 확인 = 그 매장 이름을 헤더로 한 액션 메뉴 카드
            return build_action_menu(
                directory, header=f"{directory.name_of(selected)} · 무엇이 궁금하세요?"
            )
        return build_store_picker(directory.list())

    # 4) 단일 매장/미설정이면 기본 매장
    if not store_id:
        store_id = get_settings().default_store_id

    # 매장은 정해졌는데 발화가 비었으면(채널 진입 등) 액션 메뉴
    if not utterance:
        return build_action_menu(directory)

    logger.info("kakao 질문 store=%s: %s", store_id, utterance)

    # LLM 답변은 5초를 넘길 수 있다. 콜백이 켜져 있으면(callbackUrl 존재) 즉시 '확인 중'을
    # 주고 백그라운드로 답을 만들어 콜백으로 보낸다 → 카카오 타임아웃('멈춤')을 피한다.
    callback_url = extract_callback_url(payload)
    if callback_url:
        background_tasks.add_task(
            _send_kakao_callback, callback_url, utterance, store_id, directory
        )
        return build_callback_ack()

    # 콜백이 없으면(오픈빌더에서 콜백 미사용) 동기로 답한다.
    answer = _answer_text(utterance, store_id)
    logger.info("kakao 답변 store=%s: %s", store_id, answer)
    return build_answer(answer, directory)


@app.post(
    "/scene-suggestions",
    response_model=SceneSuggestionResponse,
    tags=["scene"],
)
def create_scene_suggestion(
    req: SceneImageRequest,
    user: CurrentUser = Depends(get_current_user),
) -> Any:
    """CCTV 한 장에서 테이블·카운터·좌석의 편집용 초안을 만든다."""
    if user.role != ADMIN_ROLE and req.store_id != user.store_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="담당 매장에만 접근할 수 있습니다",
        )
    expected_camera_id = f"{req.store_id}-cam1"
    if req.camera_id != expected_camera_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"camera_id는 {expected_camera_id}여야 합니다",
        )
    try:
        return generate_scene_suggestion(req)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except SceneSuggestionUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "scene_suggestion_unavailable",
                "message": f"장면 초안을 생성하지 못했습니다: {exc}",
            },
        ) from exc
