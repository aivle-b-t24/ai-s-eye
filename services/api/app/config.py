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
    return Path(__file__).resolve().parents[3] / "samples"


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
