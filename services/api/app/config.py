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
    vision_snapshot_dir: Path
    vision_snapshot_max_bytes: int
    store_media_dir: Path
    store_media_max_bytes: int
    vision_store_ids: set[str]
    auth_required: bool
    firebase_project_id: str | None
    firebase_credentials_path: Path | None
    internal_api_key: str | None


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


def _default_vision_snapshot_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "vision"


def _default_store_media_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "store-media"


@lru_cache
def get_settings() -> Settings:
    origins = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    vision_store_ids = os.getenv("VISION_STORE_IDS", "store-001,store-002")
    configured_sample_dir = os.getenv("SAMPLE_DATA_DIR")
    sample_data_dir = (
        Path(configured_sample_dir)
        if configured_sample_dir
        else _default_sample_data_dir()
    )
    configured_snapshot_dir = os.getenv("VISION_SNAPSHOT_DIR")
    configured_media_dir = os.getenv("STORE_MEDIA_DIR")
    configured_firebase_credentials = os.getenv("FIREBASE_CREDENTIALS")
    vision_snapshot_dir = (
        Path(configured_snapshot_dir)
        if configured_snapshot_dir
        else _default_vision_snapshot_dir()
    )
    store_media_dir = (
        Path(configured_media_dir)
        if configured_media_dir
        else _default_store_media_dir()
    )
    return Settings(
        app_name=os.getenv("APP_NAME", "AI's Eye API"),
        app_env=os.getenv("APP_ENV", "development"),
        database_url=os.getenv("DATABASE_URL"),
        cors_origins=[origin.strip() for origin in origins.split(",") if origin.strip()],
        sample_data_dir=sample_data_dir,
        vision_snapshot_dir=vision_snapshot_dir,
        vision_snapshot_max_bytes=int(
            os.getenv("VISION_SNAPSHOT_MAX_BYTES", str(5 * 1024 * 1024))
        ),
        store_media_dir=store_media_dir,
        store_media_max_bytes=int(
            os.getenv("STORE_MEDIA_MAX_BYTES", str(200 * 1024 * 1024))
        ),
        vision_store_ids={
            store_id.strip()
            for store_id in vision_store_ids.split(",")
            if store_id.strip()
        },
        auth_required=os.getenv("AUTH_REQUIRED", "false").lower()
        in {"1", "true", "yes", "on"},
        firebase_project_id=os.getenv("FIREBASE_PROJECT_ID"),
        firebase_credentials_path=(
            Path(configured_firebase_credentials)
            if configured_firebase_credentials
            else None
        ),
        internal_api_key=os.getenv("INTERNAL_API_KEY"),
    )
