import base64
from typing import Any

import httpx
import pytest

from aicc.config import get_settings
from aicc.scene_detection import (
    SceneImageRequest,
    SceneSuggestionUnavailableError,
    decode_scene_image,
    generate_scene_suggestion,
)


def request_body() -> SceneImageRequest:
    png = base64.b64encode(b"\x89PNG\r\n\x1a\nminimal").decode()
    return SceneImageRequest(
        store_id="store-001",
        camera_id="store-001-cam1",
        image_base64=png,
        mime_type="image/png",
        image_width=1920,
        image_height=1080,
    )


def response_body() -> dict[str, Any]:
    return {
        "store_id": "store-001",
        "camera_id": "store-001-cam1",
        "source": "yolo_seg_scene_draft",
        "model": "yoloe-26s-seg.pt",
        "objects": [
            {
                "id": "yolo-table-1",
                "type": "table",
                "label": "YOLO 테이블 1",
                "polygon": [
                    {"x": 100, "y": 100},
                    {"x": 350, "y": 130},
                    {"x": 320, "y": 300},
                    {"x": 80, "y": 270},
                ],
            }
        ],
        "detections": [
            {
                "type": "table",
                "label": "YOLO 테이블 1",
                "confidence": 0.72,
                "support_frames": 4,
            }
        ],
        "warnings": ["사람이 확인해야 합니다."],
        "analyzed_frame_count": 10,
    }


def test_scene_suggestion_is_proxied_to_yolo_service(monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key")
    monkeypatch.setenv("AICC_VISION_SCENE_URL", "http://vision.test/internal/scene-suggestions")
    get_settings.cache_clear()
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("X-Internal-API-Key")
        return httpx.Response(200, json=response_body())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = generate_scene_suggestion(request_body(), client=client)

    assert result.source == "yolo_seg_scene_draft"
    assert result.model == "yoloe-26s-seg.pt"
    assert result.analyzed_frame_count == 10
    assert result.objects[0].polygon[1].y == 130
    assert seen == {
        "url": "http://vision.test/internal/scene-suggestions",
        "key": "test-internal-key",
    }
    get_settings.cache_clear()


def test_scene_suggestion_converts_worker_failure(monkeypatch) -> None:
    monkeypatch.setenv("AICC_VISION_SCENE_URL", "http://vision.test/internal/scene-suggestions")
    get_settings.cache_clear()

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "model unavailable"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SceneSuggestionUnavailableError):
            generate_scene_suggestion(request_body(), client=client)
    get_settings.cache_clear()


def test_decode_scene_image_checks_base64_and_mime_signature() -> None:
    tiny_png = b"\x89PNG\r\n\x1a\n" + b"test"
    assert decode_scene_image(base64.b64encode(tiny_png).decode(), "image/png") == tiny_png

    with pytest.raises(ValueError, match="base64"):
        decode_scene_image("not-base64", "image/png")
    with pytest.raises(ValueError, match="MIME"):
        decode_scene_image(base64.b64encode(tiny_png).decode(), "image/jpeg")


def test_scene_suggestion_defaults_missing_seat_anchors(monkeypatch) -> None:
    monkeypatch.setenv("AICC_VISION_SCENE_URL", "http://vision.test/internal/scene-suggestions")
    get_settings.cache_clear()
    payload = response_body()
    assert "seat_anchors" not in payload

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = generate_scene_suggestion(request_body(), client=client)

    assert result.seat_anchors == []
    get_settings.cache_clear()

