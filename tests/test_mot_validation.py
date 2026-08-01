from pathlib import Path
import sys

import pytest


np = pytest.importorskip("numpy")

VISION_WORKER = Path(__file__).resolve().parents[1] / "services" / "vision-worker"
sys.path.insert(0, str(VISION_WORKER))

from cafe_tracking import CafeFrame  # noqa: E402
from analyze_missed_detections import occlusion_coverage  # noqa: E402
from evaluate_mot_tracking import (  # noqa: E402
    LabeledFrame,
    compact_ids,
    load_windows,
    materialize_windows,
    normalized_gt_rows,
    pixel_boxes,
    prediction_id,
    discontinuity_id_reuse,
    stitch_segment_identities,
)


def labeled_frame(*, reset_before=False, reset_reason=None, epoch=0):
    source = CafeFrame(
        clip="5",
        segment=1,
        path=Path("frame.jpg"),
        frame_number=0,
        source_seconds=0.0,
        reset_before=reset_before,
        reset_reason=reset_reason,
    )
    return LabeledFrame(
        source=source,
        epoch=epoch,
        boxes=np.asarray([[0.1, 0.2, 0.4, 0.8]]),
        ids=np.asarray([1 + epoch * 100_000]),
    )


def test_validation_manifest_has_fixed_tune_and_test_splits():
    windows = load_windows(VISION_WORKER / "mot_validation_windows.json")

    assert len(windows) == 16
    for camera in ("5", "21"):
        camera_windows = [window for window in windows if window.camera == camera]
        assert sum(window.split == "tune" for window in camera_windows) == 4
        assert sum(window.split == "test" for window in camera_windows) == 4
        assert sum(window.category == "scene_cut" for window in camera_windows) == 2
        assert all(window.frame_count == 75 for window in camera_windows)


def test_compact_ids_preserves_identity_and_pixel_scaling():
    ids, count = compact_ids([np.asarray([100_003, 7]), np.asarray([7])])

    assert count == 2
    assert ids[0].tolist() == [1, 0]
    assert ids[1].tolist() == [0]
    assert pixel_boxes(np.asarray([[0.1, 0.2, 0.4, 0.8]]), 1000, 500).tolist() == [
        [100.0, 100.0, 400.0, 400.0]
    ]


def test_prediction_epoch_prevents_id_reuse_across_scene_cut():
    assert prediction_id(4, 0, True) == 4
    assert prediction_id(4, 1, True) == 100_004
    assert prediction_id(4, 1, False) == 4

    frames = [
        labeled_frame(),
        labeled_frame(reset_before=True, reset_reason="scene_cut", epoch=1),
    ]
    baseline = {"sequence": [{"ids": [4]}, {"ids": [4]}]}
    candidate = {"sequence": [{"ids": [4]}, {"ids": [100_004]}]}

    assert discontinuity_id_reuse({"sequence": frames}, baseline)["reused_ids"] == 1
    assert discontinuity_id_reuse({"sequence": frames}, candidate)["reused_ids"] == 0


def test_materialize_rejects_scene_cut_in_normal_window():
    manifest = load_windows(VISION_WORKER / "mot_validation_windows.json")
    window = manifest[0]
    fake_frames = [labeled_frame() for _ in range(window.start_index + window.frame_count)]
    cut_index = window.start_index + 10
    fake_frames[cut_index] = labeled_frame(
        reset_before=True,
        reset_reason="scene_cut",
        epoch=1,
    )

    with pytest.raises(ValueError, match="일반 window에 장면 전환"):
        materialize_windows([window], {window.camera: fake_frames})


def test_normalized_gt_rows_removes_degenerate_placeholders():
    frame = labeled_frame().source
    ground_truth = {
        (5, 1): {
            0: [
                [1, 0.1, 0.2, 0.4, 0.8],
                [2, -0.01, -0.01, -0.01, -0.01],
            ]
        }
    }

    rows = normalized_gt_rows(ground_truth, "5", frame)

    assert rows.shape == (1, 5)
    assert rows[:, 0].tolist() == [1]


def test_stitch_segment_identities_preserves_people_when_local_ids_permute():
    previous_boxes = np.asarray(
        [[0.1, 0.1, 0.3, 0.8], [0.6, 0.2, 0.8, 0.9]], dtype=float
    )
    previous_ids = np.asarray([101, 202])
    current_rows = np.asarray(
        [
            [8, 0.61, 0.2, 0.81, 0.9],
            [3, 0.11, 0.1, 0.31, 0.8],
        ],
        dtype=float,
    )
    allocated = iter(range(1000, 1010))

    mapping, audit = stitch_segment_identities(
        previous_boxes, previous_ids, current_rows, lambda: next(allocated)
    )

    assert mapping == {8: 202, 3: 101}
    assert audit["matched_count"] == 2
    assert audit["new_identity_count"] == 0


def test_stitch_segment_identities_gives_far_newcomer_a_new_global_id():
    previous_boxes = np.asarray([[0.05, 0.05, 0.15, 0.35]], dtype=float)
    previous_ids = np.asarray([101])
    current_rows = np.asarray([[9, 0.8, 0.6, 0.95, 0.98]], dtype=float)

    mapping, audit = stitch_segment_identities(
        previous_boxes, previous_ids, current_rows, lambda: 303
    )

    assert mapping == {9: 303}
    assert audit["matched_count"] == 0
    assert audit["new_identity_count"] == 1


def test_occlusion_coverage_distinguishes_overlap_from_clear_person():
    boxes = np.asarray(
        [
            [0, 0, 100, 100],
            [50, 0, 150, 100],
            [300, 0, 400, 100],
        ],
        dtype=float,
    )

    coverage = occlusion_coverage(boxes)

    assert coverage.tolist() == [0.5, 0.5, 0.0]
