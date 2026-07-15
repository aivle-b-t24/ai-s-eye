from functools import lru_cache
import os

from pydantic import BaseModel


class Settings(BaseModel):
    api_base_url: str
    request_timeout_seconds: float
    default_store_id: str


@lru_cache
def get_settings() -> Settings:
    base_url = os.getenv("AICC_API_BASE_URL", "http://localhost:8000")
    return Settings(
        api_base_url=base_url.rstrip("/"),
        request_timeout_seconds=float(os.getenv("AICC_REQUEST_TIMEOUT_SECONDS", "5")),
        default_store_id=os.getenv("AICC_DEFAULT_STORE_ID", "store-001"),
    )
