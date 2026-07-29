from datetime import datetime, timezone
import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "services" / "vision-worker" / "replay_states.py"
SPEC = importlib.util.spec_from_file_location("replay_states", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
replay_states = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay_states)


def sample_state() -> dict:
    return {
        "store_id": "store-001",
        "camera_id": "store-001-cam1",
        "captured_at": "2026-07-22T07:00:00Z",
        "visible_person_count": 10,
        "queue_count_estimate": 2,
        "positions": [
            {
                "x": 960,
                "y": 540,
                "zone": "waiting",
                "type": "customer",
                "track_id": 17,
            },
            {
                "x": 1920,
                "y": 1080,
                "zone": "staff",
                "type": "staff",
            },
        ],
    }


def test_prepare_state_refreshes_timestamp_without_changing_source() -> None:
    original = sample_state()
    now = datetime(2026, 7, 24, 5, 0, tzinfo=timezone.utc)

    outgoing = replay_states.prepare_state(original, captured_at=now)

    assert outgoing["captured_at"] == "2026-07-24T05:00:00+00:00"
    assert "positions" not in outgoing
    assert original["captured_at"] == "2026-07-22T07:00:00Z"
    assert outgoing is not original


def test_prepare_state_can_preserve_original_timestamp() -> None:
    original = sample_state()

    outgoing = replay_states.prepare_state(
        original,
        preserve_timestamp=True,
    )

    assert "positions" not in outgoing
    assert outgoing["captured_at"] == original["captured_at"]
    assert outgoing is not original


def test_group_states_by_tick_pairs_same_store_sequence() -> None:
    states = [
        {"store_id": "store-001", "frame": 0},
        {"store_id": "store-002", "frame": 0},
        {"store_id": "store-001", "frame": 1},
        {"store_id": "store-002", "frame": 1},
    ]

    batches = replay_states.group_states_by_tick(states)

    assert batches == [
        [
            {"store_id": "store-001", "frame": 0},
            {"store_id": "store-002", "frame": 0},
        ],
        [
            {"store_id": "store-001", "frame": 1},
            {"store_id": "store-002", "frame": 1},
        ],
    ]


def test_group_states_by_tick_handles_different_store_lengths() -> None:
    states = [
        {"store_id": "store-001", "frame": 0},
        {"store_id": "store-002", "frame": 0},
        {"store_id": "store-001", "frame": 1},
    ]

    batches = replay_states.group_states_by_tick(states)

    assert batches[0] == [
        {"store_id": "store-001", "frame": 0},
        {"store_id": "store-002", "frame": 0},
    ]
    assert batches[1] == [{"store_id": "store-001", "frame": 1}]


def test_prepare_occupancy_normalizes_positions_and_maps_states() -> None:
    original = sample_state()
    now = datetime(2026, 7, 24, 5, 0, tzinfo=timezone.utc)

    frame = replay_states.prepare_occupancy(original, captured_at=now)

    assert frame["store_id"] == "store-001"
    assert frame["camera_id"] == "store-001-cam1"
    assert frame["captured_at"] == "2026-07-24T05:00:00+00:00"
    assert frame["coordinate_space"] == "normalized_image"
    assert frame["agents"][0] == {
        "id": "17",
        "x": 0.5,
        "y": 0.5,
        "role": "customer",
        "state": "queue",
        "zone": "waiting",
    }
    assert frame["agents"][1]["role"] == "staff"
    assert frame["agents"][1]["state"] == "working"
    assert frame["agents"][1]["x"] < 1
    assert frame["agents"][1]["y"] < 1


def test_prepare_occupancy_can_clear_positions() -> None:
    original = sample_state()
    original["positions"] = []

    frame = replay_states.prepare_occupancy(
        original,
        preserve_timestamp=True,
    )

    assert frame["captured_at"] == original["captured_at"]
    assert frame["agents"] == []


def test_waiting_zone_does_not_overstate_detected_queue() -> None:
    original = sample_state()
    original["queue_count_estimate"] = 0

    frame = replay_states.prepare_occupancy(
        original,
        preserve_timestamp=True,
    )

    assert frame["agents"][0]["zone"] == "waiting"
    assert frame["agents"][0]["state"] == "waiting"


def test_seating_zone_without_pose_confirmation_remains_unknown() -> None:
    original = sample_state()
    original["positions"][0]["zone"] = "seating"
    original["queue_count_estimate"] = 0

    frame = replay_states.prepare_occupancy(
        original,
        preserve_timestamp=True,
    )

    assert frame["agents"][0]["zone"] == "seating"
    assert frame["agents"][0]["state"] == "unknown"


def test_explicit_pose_state_is_preserved() -> None:
    original = sample_state()
    original["positions"][0].update({
        "zone": "seating",
        "state": "seated",
    })
    original["queue_count_estimate"] = 0

    frame = replay_states.prepare_occupancy(
        original,
        preserve_timestamp=True,
    )

    assert frame["agents"][0]["state"] == "seated"


def test_normalize_coordinate_clamps_image_boundaries() -> None:
    assert replay_states.normalize_coordinate(-10, 1920) == 0
    assert replay_states.normalize_coordinate(1920, 1920) == round(1919 / 1920, 6)


def test_legacy_tracker_keeps_ids_when_detection_order_changes() -> None:
    tracker = replay_states.LegacyPositionTracker(max_distance=100)
    first = [
        {"x": 100, "y": 100, "type": "customer"},
        {"x": 500, "y": 500, "type": "customer"},
    ]
    second = [
        {"x": 505, "y": 500, "type": "customer"},
        {"x": 105, "y": 100, "type": "customer"},
    ]

    first_tracked = tracker.assign(first)
    second_tracked = tracker.assign(second)

    assert first_tracked[0]["track_id"] == second_tracked[1]["track_id"]
    assert first_tracked[1]["track_id"] == second_tracked[0]["track_id"]


def test_legacy_tracker_preserves_real_track_ids() -> None:
    tracker = replay_states.LegacyPositionTracker()
    positions = [
        {"x": 100, "y": 100, "type": "customer", "track_id": 17},
    ]

    tracked = tracker.assign(positions)

    assert tracked[0]["track_id"] == 17


def test_prepare_occupancy_can_namespace_ids_between_loop_cycles() -> None:
    original = sample_state()

    frame = replay_states.prepare_occupancy(
        original,
        preserve_timestamp=True,
        id_prefix="cycle-2",
    )

    assert frame["agents"][0]["id"] == "cycle-2:17"
