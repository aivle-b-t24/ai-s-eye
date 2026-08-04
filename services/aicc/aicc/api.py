"""AICC 슈퍼바이저 인사이트 API.

기간을 받아 공통 API의 집계(GET /api/stores/summary)를 부르고,
그 결과를 Gemini로 분석해(generate_insights) 슈퍼바이저용 인사이트를 돌려준다.

오류는 원인별로 구분한다:
- 입력 형식 오류        → 422 (FastAPI 검증)
- 공통(집계) API 오류    → 502 store_api_error
- Gemini(분석) 오류      → 503 insights_unavailable
"""

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

from .agent import StoreAgent
from .auth import ADMIN_ROLE, CurrentUser, get_current_user, require_admin
from .client import StoreApiClient
from .config import get_settings
from .errors import ToolError
from .franchise_insights import InsightsUnavailableError, generate_insights
from .kakao import (
    DEFAULT_QUICK_REPLIES,
    ERROR_TEXT,
    GREETING_TEXT,
    build_skill_response,
    coerce_payload,
    extract_utterance,
    resolve_store_id,
)

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


class ChatRequest(BaseModel):
    """챗봇 질문. question은 필수, 너무 긴 입력은 막는다(토큰 낭비 방지)."""

    question: str = Field(min_length=1, max_length=500, description="고객 질문")
    store_id: str | None = Field(default=None, description="매장 ID. 없으면 기본 매장")

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = StoreApiClient()
    app.state.agent = StoreAgent()
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

    # 2) Gemini로 분석
    try:
        result = generate_insights(summary)
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
    try:
        result = app.state.agent.ask(req.question, target_store_id)
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


@app.post("/kakao/skill", tags=["kakao"])
async def kakao_skill(
    request: Request,
    x_kakao_skill_token: str | None = Header(default=None),
    token: str | None = Query(default=None),
) -> Any:
    """카카오톡 채널의 손님 질문을 받아 스킬 응답(2.0)으로 답한다.

    질문 이해·조회·답변은 /chat과 같은 StoreAgent가 처리한다. 여기서는 카카오 형식
    변환과, 어떤 상황에도 손님에게 문장을 보여주기 위한 200 보장만 담당한다.

    요청 본문은 Pydantic 모델 파라미터로 받지 않고 직접 관대하게 파싱한다. 모델
    파라미터로 받으면 검증 실패가 FastAPI 단계 422로 튀어(카카오가 거부) 200 보장이
    깨지기 때문이다.
    """
    _verify_kakao_token(x_kakao_skill_token, token)

    try:
        body = await request.json()
    except Exception:
        body = None
    payload = coerce_payload(body)

    utterance = extract_utterance(payload)
    if not utterance:
        # 채널 진입 등 빈 발화 → 인사 + 자주 묻는 질문 버튼
        return build_skill_response(GREETING_TEXT, DEFAULT_QUICK_REPLIES)

    store_id = resolve_store_id(payload, get_settings().default_store_id)
    logger.info("kakao 질문 store=%s: %s", store_id, utterance)
    try:
        result = app.state.agent.ask(utterance, store_id)
        answer = (result.get("answer") or "").strip() or ERROR_TEXT
    except Exception as exc:
        # 카카오는 비-200이면 시스템 오류만 보여준다. 안내가 사라지지 않도록
        # 오류를 삼키고 정중한 문장 200으로 답한다(원인은 로그로 남긴다).
        logger.warning("kakao 실패 store=%s: %s", store_id, exc, exc_info=True)
        answer = ERROR_TEXT
    logger.info("kakao 답변 store=%s: %s", store_id, answer)
    return build_skill_response(answer, DEFAULT_QUICK_REPLIES)
