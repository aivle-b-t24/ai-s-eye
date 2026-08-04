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

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

from .agent import StoreAgent
from .auth import ADMIN_ROLE, CurrentUser, get_current_user, require_admin
from .client import StoreApiClient
from .config import get_settings
from .errors import ToolError
from .franchise_insights import InsightsUnavailableError, generate_insights
from .scene_detection import (
    SceneImageRequest,
    SceneSuggestionResponse,
    SceneSuggestionUnavailableError,
    generate_scene_suggestion,
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
