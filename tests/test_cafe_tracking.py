import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "services" / "vision-worker" / "cafe_tracking.py"
SPEC = importlib.util.spec_from_file_location("cafe_tracking", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
cafe_tracking = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cafe_tracking
SPEC.loader.exec_module(cafe_tracking)


def make_segment(root: Path, clip: str, segment: int) -> None:
    segment_path = root / clip / str(segment)
    images = segment_path / "images"
    images.mkdir(parents=True)
    for frame_number in (0, 6, 12):
        (images / f"frames_{frame_number}.jpg").touch()
    (segment_path / "ann.json").write_text(
        json.dumps({"fps": 30, "framesEach": 6, "framesCount": 3}),
        encoding="utf-8",
    )


def test_iter_camera_frames_preserves_order_time_and_resets(tmp_path: Path) -> None:
    for segment in (0, 1, 3):
        make_segment(tmp_path, "5", segment)

    frames = list(
        cafe_tracking.iter_camera_frames(
            tmp_path,
            "5",
            scene_cuts={1},
        )
    )

    assert [(frame.segment, frame.frame_number) for frame in frames] == [
        (0, 0), (0, 6), (0, 12),
        (1, 0), (1, 6), (1, 12),
        (3, 0), (3, 6), (3, 12),
    ]
    assert [frame.source_seconds for frame in frames[::3]] == pytest.approx(
        [0.0, 0.6, 1.2]
    )
    assert [frame.reset_reason for frame in frames[::3]] == [
        "initial",
        "scene_cut",
        "segment_gap",
    ]


def test_iter_camera_frames_keeps_tracker_across_contiguous_segments(tmp_path: Path) -> None:
    for segment in (0, 1):
        make_segment(tmp_path, "5", segment)

    frames = list(cafe_tracking.iter_camera_frames(tmp_path, "5"))

    assert [frame.reset_reason for frame in frames[::3]] == [
        "initial",
        None,
    ]
    assert [frame.reset_before for frame in frames[::3]] == [True, False]


def test_output_sampler_uses_source_time_and_forces_cut_frame() -> None:
    sampler = cafe_tracking.OutputSampler(1.0)

    emitted = [
        value
        for value in (0.0, 0.2, 0.8, 1.0, 1.8, 2.0)
        if sampler.should_emit(value)
    ]
    assert emitted == [0.0, 1.0, 2.0]
    assert sampler.should_emit(2.4, force=True)
    assert not sampler.should_emit(3.0)
    assert sampler.should_emit(3.4)


def test_tracking_epoch_namespaces_ids_after_reset() -> None:
    epoch = cafe_tracking.TrackingEpoch("store-001-cam1")
    epoch.reset()
    first = epoch.public_id(17)
    epoch.reset()
    second = epoch.public_id(17)

    assert first == "store-001-cam1:e0:t17"
    assert second == "store-001-cam1:e1:t17"
    assert first != second


def test_validate_model_file_requires_expected_weight(tmp_path: Path) -> None:
    model = tmp_path / "best.pt"
    model.write_bytes(b"model-under-test")
    digest = hashlib.sha256(model.read_bytes()).hexdigest()

    assert cafe_tracking.validate_model_file(model, digest) == digest
    with pytest.raises(ValueError, match="SHA-256"):
        cafe_tracking.validate_model_file(model, "0" * 64)
    with pytest.raises(FileNotFoundError, match="AISEYE_CAFE_MODEL"):
        cafe_tracking.validate_model_file(tmp_path / "missing.pt", digest)


def test_reset_ultralytics_tracker_resets_all_camera_trackers() -> None:
    class Tracker:
        def __init__(self) -> None:
            self.calls = 0

        def reset(self) -> None:
            self.calls += 1

    trackers = [Tracker(), Tracker()]
    model = type(
        "Model",
        (),
        {"predictor": type("Predictor", (), {"trackers": trackers})()},
    )()

    cafe_tracking.reset_ultralytics_tracker(model)

    assert [tracker.calls for tracker in trackers] == [1, 1]
