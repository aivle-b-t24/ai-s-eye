from fastapi.testclient import TestClient

from app.models import OperationsSimulationScenario
from app.operations_simulation import run_operations_simulation


def _scenario(**changes) -> OperationsSimulationScenario:
    values = {
        "name": "테스트",
        "store_id": "store-001",
        "duration_minutes": 120,
        "staff_count": 1,
        "arrivals_per_hour": 38,
        "event_multiplier": 1.5,
        "average_service_minutes": 4.5,
        "service_variability": 0.2,
        "patience_minutes": 7,
        "seat_count": 12,
        "dine_in_rate": 0.6,
        "seed": 4512,
    }
    values.update(changes)
    return OperationsSimulationScenario(**values)


def test_simulation_is_deterministic() -> None:
    first = run_operations_simulation(_scenario())
    second = run_operations_simulation(_scenario())

    assert first.run_id == second.run_id
    assert first.metrics == second.metrics
    assert first.frames == second.frames
    assert first.source == "simulation"


def test_more_staff_improves_high_demand_scenario() -> None:
    one_staff = run_operations_simulation(_scenario(staff_count=1))
    two_staff = run_operations_simulation(_scenario(staff_count=2))

    assert two_staff.metrics.visitors == one_staff.metrics.visitors
    assert two_staff.metrics.completed_orders > one_staff.metrics.completed_orders
    assert two_staff.metrics.abandoned_orders < one_staff.metrics.abandoned_orders
    assert two_staff.metrics.average_wait_minutes < one_staff.metrics.average_wait_minutes


def test_simulation_api_returns_playback_frames(client: TestClient) -> None:
    response = client.post(
        "/api/simulations/operations",
        json=_scenario().model_dump(mode="json"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "simulation"
    assert body["run_id"].startswith("sim-")
    assert body["frames"]
    assert body["frames"][0]["agents"][0]["role"] == "staff"
    assert "저장하지 않습니다" in body["assumptions"][-1]


def test_simulation_api_rejects_unknown_store(client: TestClient) -> None:
    response = client.post(
        "/api/simulations/operations",
        json=_scenario(store_id="store-unknown").model_dump(mode="json"),
    )

    assert response.status_code == 404
