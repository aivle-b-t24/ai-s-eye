from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.main import settings


JPEG_IMAGE = b"\xff\xd8\xff\xe0store-001-image\xff\xd9"
PNG_IMAGE = b"\x89PNG\r\n\x1a\nstore-002-image"


@pytest.fixture
def snapshot_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "vision_snapshot_dir", tmp_path)
    return tmp_path


def test_snapshots_are_saved_and_read_separately_by_store(
    client: TestClient,
    snapshot_dir: Path,
) -> None:
    store_one_upload = client.post(
        "/internal/stores/store-001/vision-snapshot",
        files={"image": ("store-001.jpg", JPEG_IMAGE, "image/jpeg")},
    )
    store_two_upload = client.post(
        "/internal/stores/store-002/vision-snapshot",
        files={"image": ("store-002.png", PNG_IMAGE, "image/png")},
    )

    store_one_read = client.get("/api/stores/store-001/vision/latest")
    store_two_read = client.get("/api/stores/store-002/vision/latest")

    assert store_one_upload.status_code == 201
    assert store_two_upload.status_code == 201
    assert store_one_upload.json()["image_url"] == (
        "/api/stores/store-001/vision/latest"
    )
    assert store_two_upload.json()["content_type"] == "image/png"
    assert store_one_read.status_code == 200
    assert store_one_read.content == JPEG_IMAGE
    assert store_one_read.headers["content-type"] == "image/jpeg"
    assert store_one_read.headers["cache-control"] == "no-store"
    assert store_two_read.status_code == 200
    assert store_two_read.content == PNG_IMAGE
    assert store_two_read.headers["content-type"] == "image/png"
    assert (snapshot_dir / "store-001" / "latest").read_bytes() == JPEG_IMAGE
    assert (snapshot_dir / "store-002" / "latest").read_bytes() == PNG_IMAGE


def test_new_snapshot_replaces_previous_image(
    client: TestClient,
    snapshot_dir: Path,
) -> None:
    first_image = b"\xff\xd8\xff\xe0first\xff\xd9"
    second_image = b"\xff\xd8\xff\xe0second\xff\xd9"

    client.post(
        "/internal/stores/store-001/vision-snapshot",
        files={"image": ("first.jpg", first_image, "image/jpeg")},
    )
    response = client.post(
        "/internal/stores/store-001/vision-snapshot",
        files={"image": ("second.jpg", second_image, "image/jpeg")},
    )

    assert response.status_code == 201
    assert client.get("/api/stores/store-001/vision/latest").content == second_image
    assert (snapshot_dir / "store-001" / "latest").read_bytes() == second_image


def test_raw_snapshot_is_kept_separately_from_analysis_snapshot(
    client: TestClient,
    snapshot_dir: Path,
) -> None:
    client.post(
        "/internal/stores/store-001/vision-snapshot",
        files={"image": ("analysis.jpg", JPEG_IMAGE, "image/jpeg")},
    )
    raw_image = b"\xff\xd8\xff\xe0raw-image\xff\xd9"

    upload = client.post(
        "/internal/stores/store-001/vision-raw",
        files={"image": ("raw.jpg", raw_image, "image/jpeg")},
    )
    read = client.get("/api/stores/store-001/vision/raw/latest")

    assert upload.status_code == 201
    assert upload.json()["image_url"] == (
        "/api/stores/store-001/vision/raw/latest"
    )
    assert read.status_code == 200
    assert read.content == raw_image
    assert client.get("/api/stores/store-001/vision/latest").content == JPEG_IMAGE
    assert (snapshot_dir / "store-001" / "latest-raw").read_bytes() == raw_image


def test_missing_raw_snapshot_returns_404(
    client: TestClient,
    snapshot_dir: Path,
) -> None:
    response = client.get("/api/stores/store-001/vision/raw/latest")

    assert response.status_code == 404
    assert response.json()["detail"] == "Raw vision snapshot not found"


def test_missing_snapshot_returns_404(
    client: TestClient,
    snapshot_dir: Path,
) -> None:
    response = client.get("/api/stores/store-001/vision/latest")

    assert response.status_code == 404
    assert response.json()["detail"] == "Vision snapshot not found"


def test_unknown_store_is_rejected(
    client: TestClient,
    snapshot_dir: Path,
) -> None:
    upload_response = client.post(
        "/internal/stores/store-999/vision-snapshot",
        files={"image": ("unknown.jpg", JPEG_IMAGE, "image/jpeg")},
    )
    read_response = client.get("/api/stores/store-999/vision/latest")

    assert upload_response.status_code == 404
    assert read_response.status_code == 404
    assert not list(snapshot_dir.iterdir())


def test_non_image_upload_is_rejected(
    client: TestClient,
    snapshot_dir: Path,
) -> None:
    response = client.post(
        "/internal/stores/store-001/vision-snapshot",
        files={"image": ("notes.txt", b"not an image", "text/plain")},
    )

    assert response.status_code == 415
    assert response.json()["detail"] == "Only JPEG and PNG images are supported"
    assert not list(snapshot_dir.iterdir())


def test_oversized_image_is_rejected(
    client: TestClient,
    snapshot_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "vision_snapshot_max_bytes", 8)

    response = client.post(
        "/internal/stores/store-001/vision-snapshot",
        files={"image": ("large.jpg", JPEG_IMAGE, "image/jpeg")},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "Image is too large"
    assert not list(snapshot_dir.iterdir())
