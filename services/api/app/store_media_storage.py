"""업로드 미디어 파일 저장 경로 유틸."""

from pathlib import Path
import re
import uuid

SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def default_store_media_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "store-media"


def media_absolute_path(root: Path, store_id: str, media_id: str, filename: str) -> Path:
    safe = SAFE_NAME.sub("_", filename).strip("._") or "upload.bin"
    return root / store_id / media_id / safe


def new_media_id() -> str:
    return str(uuid.uuid4())


def save_media_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def read_media_bytes(path: Path) -> bytes:
    return path.read_bytes()
