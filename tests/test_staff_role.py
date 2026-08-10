from pathlib import Path
import sys

import pytest


np = pytest.importorskip("numpy")


VISION_WORKER = Path(__file__).resolve().parents[1] / "services" / "vision-worker"
sys.path.insert(0, str(VISION_WORKER))

from cafe_stores import (  # noqa: E402
    StaffCountState,
    StaffPresenceState,
    StaffRoleState,
    staff_candidates,
    staff_role_policy,
)
from roi_zone_counter import staff_zone_evidence  # noqa: E402


def staff_zone():
    return [
        {
            "key": "staff",
            "zid": "staff_1",
            "polygon": np.asarray([[0, 0], [100, 0], [100, 100], [0, 100]]),
        }
    ]


def test_bbox_overlap_finds_occluded_staff_when_foot_is_outside_roi():
    evidence = staff_zone_evidence([20, 40, 80, 120], staff_zone())

    assert evidence["foot_inside"] is False
    assert evidence["overlap_ratio"] >= 0.30
    assert evidence["candidate"] is True


def test_bbox_overlap_does_not_include_customer_outside_staff_roi():
    evidence = staff_zone_evidence([120, 20, 180, 100], staff_zone())

    assert evidence == {
        "candidate": False,
        "foot_inside": False,
        "overlap_ratio": 0.0,
    }


def test_staff_role_uses_three_of_five_votes_and_holds_two_misses():
    roles = StaffRoleState(window_size=5, required_votes=3)
    occluded_staff = np.asarray([[20, 40, 80, 120]], dtype=float)
    outside = np.asarray([[120, 20, 180, 100]], dtype=float)

    assert roles.update(occluded_staff, [7], staff_zone()) == [False]
    assert roles.update(occluded_staff, [7], staff_zone()) == [False]
    assert roles.update(occluded_staff, [7], staff_zone()) == [True]
    assert roles.update(outside, [7], staff_zone()) == [True]
    assert roles.update(outside, [7], staff_zone()) == [True]
    assert roles.update(outside, [7], staff_zone()) == [False]


def test_foot_inside_staff_roi_also_uses_temporal_votes():
    roles = StaffRoleState()
    box = np.asarray([[20, 10, 80, 90]], dtype=float)

    assert roles.update(box, [3], staff_zone()) == [False]
    assert roles.update(box, [3], staff_zone()) == [False]
    assert roles.update(box, [3], staff_zone()) == [True]


def test_store_staff_policies_are_camera_specific():
    assert staff_role_policy("store-001") == {
        "use_bbox": True,
        "bbox_overlap_threshold": 0.80,
    }
    assert staff_role_policy("store-002") == {
        "use_bbox": True,
        "bbox_overlap_threshold": 0.20,
        "max_active_staff": 1,
        "locked_bbox_overlap_threshold": 0.20,
        "lock_grace_updates": 10,
    }


def test_store_002_uses_bbox_overlap_when_foot_is_hidden_by_counter():
    box = np.asarray([[20, 40, 80, 120]], dtype=float)

    assert staff_candidates(box, staff_zone(), "store-002") == [True]


def test_single_staff_lock_prefers_foot_candidate_and_suppresses_customer():
    roles = StaffRoleState(
        max_active_staff=1,
        locked_bbox_overlap_threshold=0.20,
    )
    staff = [20, 10, 80, 90]
    customer_at_counter = [30, 60, 90, 140]
    boxes = np.asarray([staff, customer_at_counter], dtype=float)

    roles.update(boxes, [1, 2], staff_zone(), bbox_overlap_threshold=0.20)
    roles.update(boxes, [1, 2], staff_zone(), bbox_overlap_threshold=0.20)
    flags = roles.update(boxes, [1, 2], staff_zone(), bbox_overlap_threshold=0.20)

    assert flags == [True, False]


def test_single_staff_lock_survives_short_bbox_occlusion_then_releases():
    roles = StaffRoleState(
        window_size=3,
        required_votes=2,
        max_active_staff=1,
        locked_bbox_overlap_threshold=0.20,
        lock_grace_updates=2,
    )
    behind_counter = np.asarray([[20, 40, 80, 120]], dtype=float)
    outside = np.asarray([[120, 20, 180, 100]], dtype=float)

    assert roles.update(
        behind_counter, [7], staff_zone(), bbox_overlap_threshold=0.20
    ) == [False]
    assert roles.update(
        behind_counter, [7], staff_zone(), bbox_overlap_threshold=0.20
    ) == [True]
    assert roles.update(outside, [7], staff_zone(), bbox_overlap_threshold=0.20) == [False]
    assert roles.update(outside, [7], staff_zone(), bbox_overlap_threshold=0.20) == [False]
    assert roles.update(outside, [7], staff_zone(), bbox_overlap_threshold=0.20) == [False]
    assert roles.locked_track_ids == set()


def test_single_staff_lock_resets_at_scene_cut():
    roles = StaffRoleState(
        window_size=1,
        required_votes=1,
        max_active_staff=1,
    )
    box = np.asarray([[20, 10, 80, 90]], dtype=float)
    assert roles.update(box, [3], staff_zone()) == [True]

    roles.reset()

    assert roles.locked_track_ids == set()
    assert roles.update(np.empty((0, 4)), [], staff_zone()) == []


def test_saved_evidence_uses_same_single_staff_lock_as_live_boxes():
    roles = StaffRoleState(
        window_size=1,
        required_votes=1,
        max_active_staff=1,
        locked_bbox_overlap_threshold=0.20,
    )
    evidences = [
        {"foot_inside": True, "overlap_ratio": 1.0},
        {"foot_inside": False, "overlap_ratio": 0.65},
    ]

    assert roles.update_evidence(
        evidences,
        ["employee", "customer"],
        bbox_overlap_threshold=0.20,
    ) == [True, False]


def test_staff_count_holds_short_occlusion_then_expires():
    counts = StaffCountState(grace_updates=10)

    assert counts.update(1) == 1
    assert [counts.update(0) for _ in range(10)] == [1] * 10
    assert counts.update(0) == 0


def test_staff_count_reset_does_not_cross_scene_cut():
    counts = StaffCountState(grace_updates=10)
    assert counts.update(1) == 1

    counts.reset()

    assert counts.update(0) == 0


def _position(track_id, x, y, role="customer"):
    return {
        "track_id": track_id,
        "x": x,
        "y": y,
        "bbox": {"x1": x - 20, "y1": y - 80, "x2": x + 20, "y2": y},
        "type": role,
        "state": "working" if role == "staff" else "unknown",
        "zone": "staff" if role == "staff" else "seating",
    }


def test_staff_presence_keeps_same_id_and_position_during_short_occlusion():
    presence = StaffPresenceState(grace_updates=2)
    observed, count = presence.update([_position("staff-1", 100, 100, "staff")])
    hidden, hidden_count = presence.update([])

    assert count == 1
    assert observed[0].get("occluded") is None
    assert hidden_count == 1
    assert hidden[0]["track_id"] == "staff-1"
    assert hidden[0]["type"] == "staff"
    assert hidden[0]["occluded"] is True


def test_staff_presence_reclassifies_nearby_same_track_as_occluded_staff():
    presence = StaffPresenceState(grace_updates=2, exit_distance_pixels=50)
    presence.update([_position("staff-1", 100, 100, "staff")])

    held, count = presence.update([_position("staff-1", 120, 100)])

    assert count == 1
    assert len(held) == 1
    assert held[0]["type"] == "staff"
    assert held[0]["occluded"] is True


def test_staff_presence_relinks_nearby_reissued_track_id():
    presence = StaffPresenceState(grace_updates=2, exit_distance_pixels=50)
    presence.update([_position("staff-old", 100, 100, "staff")])
    presence.update([])

    relinked, count = presence.update(
        [_position("staff-new", 125, 100, "staff")]
    )

    assert count == 1
    assert relinked[0]["track_id"] == "staff-old"
    assert relinked[0]["relinked"] is True
    assert relinked[0].get("occluded") is None


def test_staff_presence_does_not_relink_distant_new_track():
    presence = StaffPresenceState(grace_updates=2, exit_distance_pixels=50)
    presence.update([_position("staff-old", 100, 100, "staff")])
    presence.update([])

    observed, count = presence.update(
        [_position("staff-new", 180, 100, "staff")]
    )

    assert count == 1
    assert observed[0]["track_id"] == "staff-new"
    assert observed[0].get("relinked") is None


def test_staff_presence_zero_entry_exit_and_next_entry_lifecycle():
    presence = StaffPresenceState(grace_updates=10, exit_distance_pixels=50)

    assert presence.update([]) == ([], 0)
    assert presence.update([_position("staff-a", 100, 100, "staff")])[1] == 1
    assert presence.update([_position("staff-a", 180, 100)])[1] == 0
    entered, count = presence.update(
        [_position("staff-b", 105, 100, "staff")]
    )

    assert count == 1
    assert entered[0]["track_id"] == "staff-b"


def test_staff_presence_releases_same_track_immediately_after_roi_exit():
    presence = StaffPresenceState(grace_updates=10, exit_distance_pixels=50)
    presence.update([_position("staff-1", 100, 100, "staff")])

    visible, count = presence.update([_position("staff-1", 180, 100)])

    assert count == 0
    assert visible[0]["type"] == "customer"
    assert visible[0].get("occluded") is None


def test_staff_presence_expires_and_scene_reset_removes_ghost():
    presence = StaffPresenceState(grace_updates=1)
    presence.update([_position("staff-1", 100, 100, "staff")])
    assert presence.update([])[1] == 1
    assert presence.update([]) == ([], 0)

    presence.update([_position("staff-2", 100, 100, "staff")])
    presence.reset()

    assert presence.update([]) == ([], 0)
