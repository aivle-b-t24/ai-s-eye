"""AICC 슈퍼바이저 인사이트 API.

기간을 받아 공통 API의 집계(GET /api/stores/summary)를 부르고,
그 결과를 Gemini로 분석해(generate_insights) 슈퍼바이저용 인사이트를 돌려준다.

오류는 원인별로 구분한다:
- 입력 형식 오류        → 422 (FastAPI 검증)
- 공통(집계) API 오류    → 502 store_api_error
- Gemini(분석) 오류      → 503 insights_unavailable
"""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

from .client import StoreApiClient
from .config import get_settings
from .errors import ToolError
from .franchise_insights import InsightsUnavailableError, generate_insights


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
    evidence: dict[str, Any] = Field(default_factory=dict)
    recommendation: str | None = None


class Comparison(BaseModel):
    summary: str | None = None
    recommendation: str | None = None


class InsightsResponse(BaseModel):
    insights: list[Insight]
    comparison: Comparison = Field(default_factory=Comparison)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = StoreApiClient()
    try:
        yield
    finally:
        app.state.client.close()


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


@app.post("/insights", response_model=InsightsResponse, tags=["insights"])
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
