from fastapi.testclient import TestClient

from app.models import (
    OperationsArrivalProfileSegment,
    OperationsComparisonRequest,
    OperationsSimulationScenario,
)
from app.operations_simulation import (
    run_operations_comparison,
    run_operations_simulation,
)


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


def _comparison_request() -> OperationsComparisonRequest:
    return OperationsComparisonRequest(
        store_id="store-001",
        duration_minutes=180,
        arrival_profile=[
            OperationsArrivalProfileSegment(
                start_minute=0,
                end_minute=60,
                arrivals_per_hour=20,
            ),
            OperationsArrivalProfileSegment(
                start_minute=60,
                end_minute=120,
                arrivals_per_hour=32,
            ),
            OperationsArrivalProfileSegment(
                start_minute=120,
                end_minute=180,
                arrivals_per_hour=24,
            ),
        ],
        event_multiplier=1.6,
        seed=20260810,
        demand_source="synthetic_order_simulator",
        demand_window_label="11:00~14:00",
    )


def test_comparison_shares_exact_event_demand() -> None:
    result = run_operations_comparison(_comparison_request())

    assert result.event_one.demand_trace_id == result.event_two.demand_trace_id
    assert result.event_demand_trace_id == result.event_one.demand_trace_id
    one_received = [
        (event.at_minute, event.customer_id, event.order_id)
        for event in result.event_one.events
        if event.event_type == "order_received"
    ]
    two_received = [
        (event.at_minute, event.customer_id, event.order_id)
        for event in result.event_two.events
        if event.event_type == "order_received"
    ]
    assert one_received == two_received
    assert result.event_one.metrics.visitors == result.event_two.metrics.visitors
    assert result.fairness.changed_parameter == "staff_count"


def test_comparison_searches_to_max_and_selects_minimum_sufficient_staff() -> None:
    request = _comparison_request().model_copy(update={"max_staff_count": 5})
    result = run_operations_comparison(request)

    assert [option.staff_count for option in result.staffing_options] == [1, 2, 3, 4, 5]
    passing = [option.staff_count for option in result.staffing_options if option.meets_targets]
    assert passing
    assert result.recommended_staff_count == min(passing)
    assert result.capacity_sufficient is True
    assert result.event_one.scenario.staff_count == request.current_staff_count
    assert result.event_two.scenario.staff_count == request.max_staff_count
    recommended = (
        result.event_one
        if result.recommended_staff_count == request.current_staff_count
        else result.event_two
        if result.recommended_staff_count == request.max_staff_count
        else result.event_recommended
    )
    assert recommended is not None
    assert recommended.scenario.staff_count == result.recommended_staff_count
    assert recommended.demand_trace_id == result.event_demand_trace_id


def test_comparison_reports_when_max_staff_cannot_meet_targets() -> None:
    request = _comparison_request().model_copy(update={
        "event_multiplier": 4,
        "max_staff_count": 2,
    })
    result = run_operations_comparison(request)

    assert result.capacity_sufficient is False
    assert result.recommended_staff_count == 2
    assert all(not option.meets_targets for option in result.staffing_options)


def test_order_lifecycle_and_half_minute_frames_are_recorded() -> None:
    result = run_operations_comparison(_comparison_request()).event_two
    event_types = {event.event_type for event in result.events}

    assert {"order_received", "queued", "preparing", "ready", "completed"} <= event_types
    assert all(agent.order_id for frame in result.frames for agent in frame.agents if agent.role == "customer")
    assert any(
        abs(current.at_minute - previous.at_minute - 0.5) < 0.001
        for previous, current in zip(result.frames, result.frames[1:])
    )
    last_counts = result.frames[-1].order_status_counts
    assert (
        last_counts.waiting
        + last_counts.preparing
        + last_counts.ready
        + last_counts.completed
        + last_counts.abandoned
        == result.metrics.visitors
    )


def test_comparison_api_returns_three_variants(client: TestClient) -> None:
    response = client.post(
        "/api/simulations/operations/compare",
        json=_comparison_request().model_dump(mode="json"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "simulation_comparison"
    assert body["normal_one"]["scenario"]["staff_count"] == 1
    assert body["event_one"]["scenario"]["staff_count"] == 1
    assert body["event_two"]["scenario"]["staff_count"] == 2
    assert body["event_one"]["demand_trace_id"] == body["event_two"]["demand_trace_id"]


def test_comparison_accepts_current_and_max_staff(client: TestClient) -> None:
    payload = _comparison_request().model_dump(mode="json")
    payload.update({"current_staff_count": 2, "max_staff_count": 5})

    response = client.post("/api/simulations/operations/compare", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["current_staff_count"] == 2
    assert body["max_staff_count"] == 5
    assert body["normal_one"]["scenario"]["staff_count"] == 2
    assert body["event_one"]["scenario"]["staff_count"] == 2
    assert body["event_two"]["scenario"]["staff_count"] == 5
    assert [option["staff_count"] for option in body["staffing_options"]] == [1, 2, 3, 4, 5]


def test_comparison_rejects_current_staff_above_maximum() -> None:
    try:
        OperationsComparisonRequest(current_staff_count=5, max_staff_count=4)
    except ValueError as exc:
        assert "current_staff_count must not exceed max_staff_count" in str(exc)
    else:
        raise AssertionError("invalid staffing range was accepted")


def test_arrival_profile_must_cover_duration() -> None:
    try:
        OperationsComparisonRequest(
            duration_minutes=180,
            arrival_profile=[
                OperationsArrivalProfileSegment(
                    start_minute=0,
                    end_minute=60,
                    arrivals_per_hour=24,
                ),
            ],
        )
    except ValueError as exc:
        assert "full duration" in str(exc)
    else:
        raise AssertionError("incomplete arrival profile was accepted")
