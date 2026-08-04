from functools import lru_cache
import os
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    api_base_url: str
    request_timeout_seconds: float
    default_store_id: str
    cors_origins: list[str]
    gemini_api_key: str | None
    gemini_model: str
    embedding_model: str
    vertex_project: str | None
    vertex_location: str
    auth_required: bool
    firebase_project_id: str | None
    firebase_credentials_path: Path | None
    internal_api_key: str | None
    vision_scene_url: str
    scene_request_timeout_seconds: float

    @property
    def use_vertex(self) -> bool:
        """Vertex AI를 쓸지 여부. 프로젝트가 지정돼 있으면 Vertex, 아니면 API 키."""
        return bool(self.vertex_project)


@lru_cache
def get_settings() -> Settings:
    base_url = os.getenv("AICC_API_BASE_URL", "http://localhost:8000")
    cors_origins = [
        origin.strip()
        for origin in os.getenv("AICC_CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]
    use_vertex = bool(os.getenv("AICC_VERTEX_PROJECT"))
    default_model = "gemini-2.5-flash" if use_vertex else "gemini-flash-lite-latest"
    firebase_credentials = os.getenv("FIREBASE_CREDENTIALS")
    return Settings(
        api_base_url=base_url.rstrip("/"),
        request_timeout_seconds=float(os.getenv("AICC_REQUEST_TIMEOUT_SECONDS", "5")),
        default_store_id=os.getenv("AICC_DEFAULT_STORE_ID", "store-001"),
        cors_origins=cors_origins,
        gemini_api_key=os.getenv("GOOGLE_API_KEY"),
        gemini_model=os.getenv("AICC_GEMINI_MODEL", default_model),
        embedding_model=os.getenv("AICC_EMBEDDING_MODEL", "text-multilingual-embedding-002"),
        vertex_project=os.getenv("AICC_VERTEX_PROJECT"),
        vertex_location=os.getenv("AICC_VERTEX_LOCATION", "us-central1"),
        auth_required=os.getenv("AUTH_REQUIRED", "false").lower()
        in {"1", "true", "yes", "on"},
        firebase_project_id=os.getenv("FIREBASE_PROJECT_ID"),
        firebase_credentials_path=(
            Path(firebase_credentials) if firebase_credentials else None
        ),
        internal_api_key=os.getenv("INTERNAL_API_KEY"),
        vision_scene_url=os.getenv(
            "AICC_VISION_SCENE_URL",
            "http://host.docker.internal:8200/internal/scene-suggestions",
        ),
        scene_request_timeout_seconds=float(
            os.getenv("AICC_SCENE_REQUEST_TIMEOUT_SECONDS", "120")
        ),
    )
