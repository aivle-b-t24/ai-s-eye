from pathlib import Path
import tempfile


JPEG_MEDIA_TYPE = "image/jpeg"
PNG_MEDIA_TYPE = "image/png"
SNAPSHOT_FILENAME = "latest"


class InvalidImageError(ValueError):
    pass


def detect_image_media_type(content: bytes) -> str:
    if content.startswith(b"\xff\xd8\xff"):
        return JPEG_MEDIA_TYPE
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG_MEDIA_TYPE
    raise InvalidImageError("Only JPEG and PNG images are supported")


def snapshot_path(root: Path, store_id: str) -> Path:
    return root / store_id / SNAPSHOT_FILENAME


def save_snapshot(root: Path, store_id: str, content: bytes) -> Path:
    store_dir = root / store_id
    store_dir.mkdir(parents=True, exist_ok=True)
    target = snapshot_path(root, store_id)

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
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()

    return target
