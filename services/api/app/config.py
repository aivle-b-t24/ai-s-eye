from functools import lru_cache
from pathlib import Path
import os

from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str
    app_env: str
    database_url: str | None
    cors_origins: list[str]
    sample_data_dir: Path


def _default_sample_data_dir() -> Path:
    """소스 실행과 컨테이너 실행 모두에서 안전한 기본 샘플 경로를 찾는다."""
    source_path = Path(__file__).resolve()
    for parent in source_path.parents:
        candidate = parent / "samples"
        if candidate.exists():
            return candidate
    # 컨테이너 단독 실행처럼 samples 볼륨이 아직 연결되지 않은 경우에도
    # 경로 계산 자체가 실패하지 않도록 API 작업 디렉터리 기준 경로를 반환한다.
    return source_path.parents[1] / "samples"


@lru_cache
def get_settings() -> Settings:
    origins = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    configured_sample_dir = os.getenv("SAMPLE_DATA_DIR")
    sample_data_dir = (
        Path(configured_sample_dir)
        if configured_sample_dir
        else _default_sample_data_dir()
    )
    return Settings(
        app_name=os.getenv("APP_NAME", "AI's Eye API"),
        app_env=os.getenv("APP_ENV", "development"),
        database_url=os.getenv("DATABASE_URL"),
        cors_origins=[origin.strip() for origin in origins.split(",") if origin.strip()],
        sample_data_dir=sample_data_dir,
    )
