"""승인된 ROI를 API→로컬 캐시→기존 JSON 순서로 불러온다."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ZONE_NAME = {
    "staff": "직원",
    "waiting": "대기",
    "entrance": "입구",
    "seating": "좌석",
}


def internal_headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    key = os.getenv("INTERNAL_API_KEY")
    if key:
        headers["X-Internal-API-Key"] = key
    return headers


def fetch_approved_config(
    api_base_url: str,
    store_id: str,
    camera_id: str,
    timeout: float = 3.0,
) -> dict[str, Any]:
    url = (
        api_base_url.rstrip("/")
        + f"/internal/stores/{store_id}/cameras/{camera_id}/roi-config"
    )
    request = urllib.request.Request(url, headers=internal_headers())
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def save_cache(path: Path, config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def load_cache(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def normalized_config_to_zone_data(
    config: dict[str, Any],
    frame_width: int,
    frame_height: int,
) -> dict[str, Any]:
    if config.get("coordinate_space") != "normalized_1000":
        raise ValueError("Unsupported ROI coordinate space")
    converted = []
    for zone in config.get("zones", []):
        zone_type = zone.get("type")
        if zone_type not in ZONE_NAME:
            continue
        polygon = [
            [
                round(float(point["x"]) / 1000 * frame_width),
                round(float(point["y"]) / 1000 * frame_height),
            ]
            for point in zone.get("polygon", [])
        ]
        if len(polygon) < 3:
            continue
        converted.append(
            {
                "name": ZONE_NAME[zone_type],
                "label": zone.get("label") or ZONE_NAME[zone_type],
                "polygon": polygon,
            }
        )
    if not converted:
        raise ValueError("ROI config has no usable zones")
    return {
        "store_id": config.get("store_id"),
        "camera_id": config.get("camera_id"),
        "version": config.get("version"),
        "source": "roi-config-api",
        "image_size": {"width": frame_width, "height": frame_height},
        "zones": converted,
    }


def load_roi_zone_data(
    *,
    api_base_url: str | None,
    store_id: str,
    camera_id: str,
    frame_width: int,
    frame_height: int,
    cache_path: Path,
    legacy_path: Path,
) -> tuple[dict[str, Any], str]:
    """승인 설정을 픽셀 좌표 구역으로 반환한다.

    반환 source는 api, cache, legacy 중 하나다.
    """
    if api_base_url:
        try:
            config = fetch_approved_config(api_base_url, store_id, camera_id)
            converted = normalized_config_to_zone_data(
                config,
                frame_width,
                frame_height,
            )
            save_cache(cache_path, config)
            return converted, "api"
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            urllib.error.URLError,
        ):
            pass

    cached = load_cache(cache_path)
    if cached is not None:
        try:
            return (
                normalized_config_to_zone_data(
                    cached,
                    frame_width,
                    frame_height,
                ),
                "cache",
            )
        except (ValueError, KeyError, TypeError):
            pass

    with legacy_path.open(encoding="utf-8-sig") as file:
        return json.load(file), "legacy"
