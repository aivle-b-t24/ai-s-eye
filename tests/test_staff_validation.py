from __future__ import annotations

import sys
from pathlib import Path

import pytest


np = pytest.importorskip("numpy")


VISION_DIR = Path(__file__).resolve().parents[1] / "services" / "vision-worker"
sys.path.insert(0, str(VISION_DIR))

from evaluate_staff_role import StaffVoteState, summarize  # noqa: E402


def test_foot_only_and_bbox_modes_share_votes_but_not_evidence():
    zones = [
        {
            "key": "staff",
            "zid": "staff-1",
            "polygon": np.asarray(
                [[0, 0], [100, 0], [100, 100], [0, 100]], dtype="int32"
            ),
        }
    ]
    box = [[20, 40, 80, 120]]
    foot = StaffVoteState("foot-only")
    hybrid = StaffVoteState("foot+bbox")
    for _ in range(3):
        foot_flags, _ = foot.update(box, [7], zones)
        hybrid_flags, _ = hybrid.update(box, [7], zones)
    assert foot_flags == [False]
    assert hybrid_flags == [True]


def test_bbox_vote_respects_configured_overlap_threshold():
    zones = [
        {
            "key": "staff",
            "zid": "staff-1",
            "polygon": np.asarray(
                [[0, 0], [100, 0], [100, 100], [0, 100]], dtype="int32"
            ),
        }
    ]
    borderline = [[20, 40, 80, 120]]
    configured = StaffVoteState("foot+bbox", overlap_threshold=0.80)

    for _ in range(3):
        flags, _ = configured.update(borderline, [7], zones)

    assert flags == [False]


def test_summarize_reports_under_and_over_counts():
    rows = [
        {"expected_staff_count": 1, "prediction": 1},
        {"expected_staff_count": 1, "prediction": 0},
        {"expected_staff_count": 1, "prediction": 2},
    ]
    result = summarize(rows, "prediction")
    assert result["exact_accuracy_percent"] == 33.333
    assert result["count_mae"] == 0.666667
    assert result["under_count_samples"] == 1
    assert result["over_count_samples"] == 1
