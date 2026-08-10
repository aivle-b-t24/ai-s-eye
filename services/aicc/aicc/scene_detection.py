"""인증된 Dashboard 요청을 YOLOE 테이블 장면 서비스로 전달한다."""

from __future__ import annotations

import base64
import binascii
import logging
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from .config import get_settings

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 5 * 1024 * 1024
SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png"}


class SceneSuggestionUnavailableError(RuntimeError):
    """YOLO 장면 서비스를 호출하거나 유효한 초안을 받지 못했을 때."""


class SceneImageRequest(BaseModel):
    store_id: str = Field(min_length=1, max_length=100)
    camera_id: str = Field(min_length=1, max_length=100)
    image_base64: str = Field(min_length=4, max_length=7_100_000)
    mime_type: Literal["image/jpeg", "image/png"]
    image_width: int = Field(gt=0, le=16_384)
    image_height: int = Field(gt=0, le=16_384)
    use_reference_frames: bool = True


class NormalizedPoint(BaseModel):
    x: int = Field(ge=0, le=1000)
    y: int = Field(ge=0, le=1000)


class SceneDraftObject(BaseModel):
    id: str
    type: Literal["table"]
    label: str
    polygon: list[NormalizedPoint] = Field(min_length=3, max_length=20)


class SceneDraftDetection(BaseModel):
    type: Literal["table"]
    label: str
    confidence: float = Field(ge=0, le=1)
    support_frames: int = Field(default=1, ge=1)


class SceneSuggestionResponse(BaseModel):
    store_id: str
    camera_id: str
    source: Literal["yolo_seg_scene_draft"] = "yolo_seg_scene_draft"
    model: str
    objects: list[SceneDraftObject]
    detections: list[SceneDraftDetection]
    warnings: list[str]
    analyzed_frame_count: int = Field(default=1, ge=1)
    # 온보딩/씬 스키마 호환: worker가 생략해도 기본 빈 목록으로 수용
    seat_anchors: list[Any] = Field(default_factory=list)


def decode_scene_image(image_base64: str, mime_type: str) -> bytes:
    """base64와 실제 이미지 시그니처를 함께 검증한다."""
    if mime_type not in SUPPORTED_IMAGE_TYPES:
        raise ValueError("JPEG 또는 PNG 이미지만 지원합니다.")
    try:
        payload = base64.b64decode(image_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("이미지 base64 형식이 올바르지 않습니다.") from exc
    if not payload:
        raise ValueError("이미지가 비어 있습니다.")
    if len(payload) > MAX_IMAGE_BYTES:
        raise ValueError("이미지는 5MB 이하여야 합니다.")
    is_jpeg = payload.startswith(b"\xff\xd8\xff")
    is_png = payload.startswith(b"\x89PNG\r\n\x1a\n")
    if (mime_type == "image/jpeg" and not is_jpeg) or (
        mime_type == "image/png" and not is_png
    ):
        raise ValueError("이미지 내용과 MIME 형식이 일치하지 않습니다.")
    return payload


def generate_scene_suggestion(
    req: SceneImageRequest,
    *,
    client: httpx.Client | None = None,
) -> SceneSuggestionResponse:
    """테이블 초안 생성을 GPU Vision 서비스에 위임한다."""
    decode_scene_image(req.image_base64, req.mime_type)
    settings = get_settings()
    headers: dict[str, str] = {}
    if settings.internal_api_key:
        headers["X-Internal-API-Key"] = settings.internal_api_key

    owns_client = client is None
    http_client = client or httpx.Client(timeout=settings.scene_request_timeout_seconds)
    try:
        response = http_client.post(
            settings.vision_scene_url,
            headers=headers,
            json=req.model_dump(),
        )
        response.raise_for_status()
        return SceneSuggestionResponse.model_validate(response.json())
    except (httpx.HTTPError, ValueError, ValidationError) as exc:
        logger.warning("YOLO 장면 서비스 호출 실패: %s", exc)
        raise SceneSuggestionUnavailableError(str(exc)) from exc
    finally:
        if owns_client:
            http_client.close()
