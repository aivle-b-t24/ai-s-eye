import json
from pathlib import Path
import sys


VISION_ROOT = Path(__file__).resolve().parents[1] / "services" / "vision-worker"
sys.path.insert(0, str(VISION_ROOT))

import roi_config_client  # noqa: E402


def config_payload() -> dict:
    return {
        "store_id": "store-001",
        "camera_id": "store-001-cam1",
        "version": 3,
        "coordinate_space": "normalized_1000",
        "zones": [
            {
                "id": "staff-1",
                "type": "staff",
                "label": "직원 구역",
                "polygon": [
                    {"x": 100, "y": 200},
                    {"x": 500, "y": 200},
                    {"x": 500, "y": 600},
                ],
            }
        ],
    }


def test_normalized_roi_is_scaled_to_current_frame() -> None:
    converted = roi_config_client.normalized_config_to_zone_data(
        config_payload(),
        frame_width=1280,
        frame_height=720,
    )

    assert converted["zones"][0]["name"] == "직원"
    assert converted["zones"][0]["polygon"] == [
        [128, 144],
        [640, 144],
        [640, 432],
    ]


def test_api_config_is_cached_and_cache_is_used_during_api_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    cache_path = tmp_path / "cache.json"
    legacy_path = tmp_path / "legacy.json"
    legacy_path.write_text(
        json.dumps(
            {
                "zones": [
                    {
                        "name": "대기",
                        "polygon": [[0, 0], [10, 0], [10, 10]],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        roi_config_client,
        "fetch_approved_config",
        lambda *_args, **_kwargs: config_payload(),
    )

    _, source = roi_config_client.load_roi_zone_data(
        api_base_url="http://api",
        store_id="store-001",
        camera_id="store-001-cam1",
        frame_width=1920,
        frame_height=1080,
        cache_path=cache_path,
        legacy_path=legacy_path,
    )

    assert source == "api"
    assert cache_path.is_file()

    def fail(*_args, **_kwargs):
        raise OSError("offline")

    monkeypatch.setattr(roi_config_client, "fetch_approved_config", fail)
    converted, source = roi_config_client.load_roi_zone_data(
        api_base_url="http://api",
        store_id="store-001",
        camera_id="store-001-cam1",
        frame_width=960,
        frame_height=540,
        cache_path=cache_path,
        legacy_path=legacy_path,
    )

    assert source == "cache"
    assert converted["zones"][0]["polygon"][0] == [96, 108]


def test_legacy_json_is_last_fallback(tmp_path: Path) -> None:
    legacy_path = tmp_path / "legacy.json"
    legacy = {
        "zones": [
            {
                "name": "대기",
                "polygon": [[0, 0], [10, 0], [10, 10]],
            }
        ]
    }
    legacy_path.write_text(json.dumps(legacy), encoding="utf-8")

    loaded, source = roi_config_client.load_roi_zone_data(
        api_base_url=None,
        store_id="store-001",
        camera_id="store-001-cam1",
        frame_width=1920,
        frame_height=1080,
        cache_path=tmp_path / "missing-cache.json",
        legacy_path=legacy_path,
    )

    assert source == "legacy"
    assert loaded == legacy
