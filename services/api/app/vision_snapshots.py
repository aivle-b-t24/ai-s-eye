import json
from pathlib import Path
import tempfile
from typing import Any


JPEG_MEDIA_TYPE = "image/jpeg"
PNG_MEDIA_TYPE = "image/png"
SNAPSHOT_FILENAME = "latest"
RAW_SNAPSHOT_FILENAME = "latest-raw"
SNAPSHOT_METADATA_FILENAME = "latest.json"
RAW_SNAPSHOT_METADATA_FILENAME = "latest-raw.json"


class InvalidImageError(ValueError):
    pass


def detect_image_media_type(content: bytes) -> str:
    if content.startswith(b"\xff\xd8\xff"):
        return JPEG_MEDIA_TYPE
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG_MEDIA_TYPE
    raise InvalidImageError("Only JPEG and PNG images are supported")


def snapshot_path(root: Path, store_id: str, *, raw: bool = False) -> Path:
    filename = RAW_SNAPSHOT_FILENAME if raw else SNAPSHOT_FILENAME
    return root / store_id / filename


def snapshot_metadata_path(
    root: Path,
    store_id: str,
    *,
    raw: bool = False,
) -> Path:
    filename = (
        RAW_SNAPSHOT_METADATA_FILENAME
        if raw
        else SNAPSHOT_METADATA_FILENAME
    )
    return root / store_id / filename


def load_snapshot_metadata(
    root: Path,
    store_id: str,
    *,
    raw: bool = False,
) -> dict[str, Any] | None:
    path = snapshot_metadata_path(root, store_id, raw=raw)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _save_metadata(
    root: Path,
    store_id: str,
    metadata: dict[str, Any],
    *,
    raw: bool,
) -> None:
    target = snapshot_metadata_path(root, store_id, raw=raw)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(target)


def save_snapshot(
    root: Path,
    store_id: str,
    content: bytes,
    *,
    raw: bool = False,
    metadata: dict[str, Any] | None = None,
) -> Path:
    store_dir = root / store_id
    store_dir.mkdir(parents=True, exist_ok=True)
    target = snapshot_path(root, store_id, raw=raw)

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=store_dir,
            prefix=".latest-",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary_path = Path(temporary.name)
        temporary_path.replace(target)
        if metadata is not None:
            _save_metadata(
                root,
                store_id,
                metadata,
                raw=raw,
            )
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()

    return target
