from pathlib import Path
from typing import Any

import pytest

from app.scenario_loader import load_scenario_file, send_scenario


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_PATH = PROJECT_ROOT / "samples" / "franchise_scenario.json"


def test_franchise_scenario_is_validated_before_sending() -> None:
    scenario = load_scenario_file(SCENARIO_PATH)

    assert scenario.scenario_id == "franchise-scenario-001"
    assert scenario.store_ids == ["store-001", "store-002"]
    assert len(scenario.states) == 8
    assert len(scenario.orders) == 6


def test_scenario_states_and_orders_are_sent_to_existing_endpoints() -> None:
    scenario = load_scenario_file(SCENARIO_PATH)
    requests: list[tuple[str, dict[str, Any]]] = []

    def fake_sender(
        url: str,
        payload: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        requests.append((url, payload))
        assert timeout == 3.0
        return {"ok": True}

    report = send_scenario(
        scenario,
        "http://api.test/",
        timeout=3.0,
        sender=fake_sender,
    )

    assert report.state_success_count == 8
    assert report.order_success_count == 6
    assert report.errors == []
    assert [url for url, _ in requests[:8]] == [
        "http://api.test/internal/store-states"
    ] * 8
    assert [url for url, _ in requests[8:]] == [
        "http://api.test/internal/order-events"
    ] * 6


def test_scenario_sender_reports_failed_item_and_continues() -> None:
    scenario = load_scenario_file(SCENARIO_PATH)

    def failing_sender(
        url: str,
        payload: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        if payload.get("event_id") == "event-002":
            raise RuntimeError("테스트 오류")
        return {"ok": True}

    report = send_scenario(scenario, "http://api.test", sender=failing_sender)

    assert report.state_success_count == 8
    assert report.order_success_count == 5
    assert report.errors == ["orders[1] 전송 실패: 테스트 오류"]


def test_invalid_scenario_is_rejected_before_sending(tmp_path: Path) -> None:
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text(
        '{"stores": [{"store_id": "store-001"}], "states": [], "orders": []}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="states 목록"):
        load_scenario_file(invalid_path)
