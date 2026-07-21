from functools import lru_cache
import os

from pydantic import BaseModel


class Settings(BaseModel):
    api_base_url: str
    request_timeout_seconds: float
    default_store_id: str
    gemini_api_key: str | None
    gemini_model: str
    vertex_project: str | None
    vertex_location: str

    @property
    def use_vertex(self) -> bool:
        """Vertex AI를 쓸지 여부. 프로젝트가 지정돼 있으면 Vertex, 아니면 API 키."""
        return bool(self.vertex_project)


@lru_cache
def get_settings() -> Settings:
    base_url = os.getenv("AICC_API_BASE_URL", "http://localhost:8000")
    use_vertex = bool(os.getenv("AICC_VERTEX_PROJECT"))
    default_model = "gemini-2.5-flash" if use_vertex else "gemini-flash-lite-latest"
    return Settings(
        api_base_url=base_url.rstrip("/"),
        request_timeout_seconds=float(os.getenv("AICC_REQUEST_TIMEOUT_SECONDS", "5")),
        default_store_id=os.getenv("AICC_DEFAULT_STORE_ID", "store-001"),
        gemini_api_key=os.getenv("GOOGLE_API_KEY"),
        gemini_model=os.getenv("AICC_GEMINI_MODEL", default_model),
        vertex_project=os.getenv("AICC_VERTEX_PROJECT"),
        vertex_location=os.getenv("AICC_VERTEX_LOCATION", "us-central1"),
    )
