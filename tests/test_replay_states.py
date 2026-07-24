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
        "captured_at": "2026-07-22T07:00:00Z",
        "visible_person_count": 10,
        "queue_count_estimate": 2,
    }


def test_prepare_state_refreshes_timestamp_without_changing_source() -> None:
    original = sample_state()
    now = datetime(2026, 7, 24, 5, 0, tzinfo=timezone.utc)

    outgoing = replay_states.prepare_state(original, captured_at=now)

    assert outgoing["captured_at"] == "2026-07-24T05:00:00+00:00"
    assert original["captured_at"] == "2026-07-22T07:00:00Z"
    assert outgoing is not original


def test_prepare_state_can_preserve_original_timestamp() -> None:
    original = sample_state()

    outgoing = replay_states.prepare_state(
        original,
        preserve_timestamp=True,
    )

    assert outgoing == original
    assert outgoing is not original
