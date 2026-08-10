"""본사 What-if 운영 비교용 결정적 이산사건 시뮬레이션.

실제 StoreState/OrderEvent 저장소에는 기록하지 않는다. 비교 시나리오는 미리
생성한 동일 수요 trace를 공유하고, 주문 상태 변화와 30초 heartbeat를 재생용으로
남긴다.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import random

import simpy

from .models import (
    OperationsArrivalProfileSegment,
    OperationsComparisonRequest,
    OperationsComparisonResult,
    OperationsOrderStatusCounts,
    OperationsSimulationEvent,
    OperationsSimulationFrame,
    OperationsSimulationMetrics,
    OperationsSimulationResult,
    OperationsSimulationScenario,
    TwinAgent,
    TwinAgentRole,
    TwinAgentState,
)


SAMPLE_MINUTES = 0.5
PICKUP_MINUTES = 0.2

STORE_LAYOUTS = {
    "store-001": {
        "staff": [(0.72, 0.32), (0.81, 0.35), (0.66, 0.29)],
        "entrance": (0.08, 0.78),
        "ordering": (0.66, 0.45),
        "queue": [(0.61, 0.52), (0.56, 0.58), (0.50, 0.64), (0.44, 0.70)],
        "waiting": [(0.70, 0.54), (0.76, 0.58), (0.82, 0.62)],
        "seats": [
            (0.15, 0.61), (0.33, 0.48), (0.37, 0.70), (0.46, 0.34),
            (0.64, 0.46), (0.85, 0.49), (0.46, 0.90), (0.57, 0.83),
        ],
        "exit": (0.04, 0.87),
    },
    "store-002": {
        "staff": [(0.18, 0.48), (0.24, 0.43), (0.13, 0.55)],
        "entrance": (0.34, 0.37),
        "ordering": (0.31, 0.56),
        "queue": [(0.38, 0.61), (0.46, 0.65), (0.54, 0.70), (0.62, 0.75)],
        "waiting": [(0.31, 0.69), (0.39, 0.75), (0.47, 0.80)],
        "seats": [
            (0.42, 0.55), (0.62, 0.53), (0.80, 0.64), (0.59, 0.88),
            (0.72, 0.82), (0.89, 0.70),
        ],
        "exit": (0.94, 0.55),
    },
}


@dataclass(frozen=True)
class DemandCustomer:
    number: int
    arrival_minute: float
    customer_id: str
    order_id: str
    patience_minutes: float
    service_minutes: float
    should_sit: bool
    stay_minutes: float


def _hash_payload(prefix: str, payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode()
    return f"{prefix}-{hashlib.sha256(encoded).hexdigest()[:12]}"


def _run_id(
    scenario: OperationsSimulationScenario,
    demand_trace_id: str | None = None,
) -> str:
    return _hash_payload(
        "sim",
        {
            "scenario": scenario.model_dump(mode="json"),
            "demand_trace_id": demand_trace_id,
        },
    )


def _default_profile(
    duration_minutes: int,
    arrivals_per_hour: float,
) -> list[OperationsArrivalProfileSegment]:
    first = duration_minutes / 3
    second = duration_minutes * 2 / 3
    return [
        OperationsArrivalProfileSegment(
            start_minute=0,
            end_minute=first,
            arrivals_per_hour=round(arrivals_per_hour * 0.8, 2),
        ),
        OperationsArrivalProfileSegment(
            start_minute=first,
            end_minute=second,
            arrivals_per_hour=round(arrivals_per_hour * 1.25, 2),
        ),
        OperationsArrivalProfileSegment(
            start_minute=second,
            end_minute=duration_minutes,
            arrivals_per_hour=round(arrivals_per_hour, 2),
        ),
    ]


def _generate_demand(
    profile: list[OperationsArrivalProfileSegment],
    *,
    multiplier: float,
    scenario: OperationsSimulationScenario,
) -> tuple[list[DemandCustomer], str]:
    arrival_rng = random.Random(f"{scenario.seed}:arrivals:{multiplier:.6f}")
    arrivals: list[float] = []
    for segment in profile:
        rate = segment.arrivals_per_hour * multiplier
        if rate <= 0:
            continue
        at_minute = segment.start_minute
        while True:
            at_minute += arrival_rng.expovariate(rate / 60)
            if at_minute >= segment.end_minute:
                break
            arrivals.append(at_minute)

    customers: list[DemandCustomer] = []
    for number, arrival_minute in enumerate(sorted(arrivals), start=1):
        customer_rng = random.Random(f"{scenario.seed}:customer:{number}")
        sigma = scenario.service_variability
        mean = scenario.average_service_minutes
        service_minutes = (
            mean
            if sigma == 0
            else customer_rng.lognormvariate(
                math.log(mean) - sigma * sigma / 2,
                sigma,
            )
        )
        customers.append(DemandCustomer(
            number=number,
            arrival_minute=round(arrival_minute, 6),
            customer_id=f"sim-customer-{number:04d}",
            order_id=f"sim-order-{number:04d}",
            patience_minutes=round(
                scenario.patience_minutes * customer_rng.uniform(0.7, 1.3),
                6,
            ),
            service_minutes=round(max(service_minutes, 0.35), 6),
            should_sit=(
                scenario.seat_count > 0
                and customer_rng.random() < scenario.dine_in_rate
            ),
            stay_minutes=round(max(customer_rng.expovariate(1 / 20), 4), 6),
        ))

    trace_payload = [asdict(customer) for customer in customers]
    return customers, _hash_payload("demand", trace_payload)


def _position_with_jitter(
    point: tuple[float, float],
    index: int,
) -> tuple[float, float]:
    column = index % 3
    row = index // 3
    return (
        min(max(point[0] + (column - 1) * 0.025, 0.02), 0.98),
        min(max(point[1] + row * 0.028, 0.02), 0.98),
    )


def _frame_agents(
    store_id: str,
    active: dict[str, TwinAgentState],
    order_ids: dict[str, str],
    staff_count: int,
) -> list[TwinAgent]:
    layout = STORE_LAYOUTS.get(store_id, STORE_LAYOUTS["store-001"])
    agents: list[TwinAgent] = []
    for index in range(staff_count):
        point = layout["staff"][index % len(layout["staff"])]
        agents.append(TwinAgent(
            id=f"sim-staff-{index + 1}",
            x=point[0],
            y=point[1],
            role=TwinAgentRole.STAFF,
            state=TwinAgentState.WORKING,
            zone="staff",
        ))

    grouped: dict[TwinAgentState, list[str]] = defaultdict(list)
    for customer_id, state in sorted(active.items()):
        grouped[state].append(customer_id)

    for state, customer_ids in grouped.items():
        for index, customer_id in enumerate(customer_ids):
            if state == TwinAgentState.QUEUE:
                base = layout["queue"][min(index, len(layout["queue"]) - 1)]
                point = _position_with_jitter(
                    base,
                    max(index - len(layout["queue"]) + 1, 0),
                )
                zone = "waiting"
            elif state == TwinAgentState.ORDERING:
                point = _position_with_jitter(layout["ordering"], index)
                zone = "waiting"
            elif state == TwinAgentState.WAITING:
                base = layout["waiting"][index % len(layout["waiting"])]
                point = _position_with_jitter(base, index // len(layout["waiting"]))
                zone = "waiting"
            elif state == TwinAgentState.SEATED:
                customer_number = int(customer_id.rsplit("-", 1)[-1])
                point = layout["seats"][(customer_number - 1) % len(layout["seats"])]
                zone = "seating"
            elif state == TwinAgentState.EXITING:
                point = _position_with_jitter(layout["exit"], index)
                zone = "entrance"
            else:
                point = _position_with_jitter(layout["entrance"], index)
                zone = "entrance"
            agents.append(TwinAgent(
                id=customer_id,
                order_id=order_ids.get(customer_id),
                x=point[0],
                y=point[1],
                role=TwinAgentRole.CUSTOMER,
                state=state,
                zone=zone,
            ))
    return agents


def _run_with_demand(
    scenario: OperationsSimulationScenario,
    demand: list[DemandCustomer],
    demand_trace_id: str,
) -> OperationsSimulationResult:
    env = simpy.Environment()
    staff = simpy.Resource(env, capacity=scenario.staff_count)
    seats = simpy.Resource(env, capacity=max(scenario.seat_count, 1))
    active: dict[str, TwinAgentState] = {}
    order_ids: dict[str, str] = {}
    order_states: dict[str, str] = {}
    frames: list[OperationsSimulationFrame] = []
    events: list[OperationsSimulationEvent] = []
    waits: list[float] = []
    completed = 0
    abandoned = 0
    max_queue = 0
    busy_minutes = 0.0
    seat_busy_minutes = 0.0
    frame_sequence = 0
    event_sequence = 0

    def status_counts() -> OperationsOrderStatusCounts:
        counts = Counter(order_states.values())
        return OperationsOrderStatusCounts(
            waiting=counts["waiting"],
            preparing=counts["preparing"],
            ready=counts["ready"],
            completed=counts["completed"],
            abandoned=counts["abandoned"],
        )

    def snapshot(at_minute: float) -> None:
        nonlocal frame_sequence
        frame_sequence += 1
        states = list(active.values())
        frames.append(OperationsSimulationFrame(
            sequence=frame_sequence,
            at_minute=round(at_minute, 3),
            queue_count=states.count(TwinAgentState.QUEUE),
            in_service_count=(
                states.count(TwinAgentState.ORDERING)
                + states.count(TwinAgentState.WAITING)
            ),
            seated_count=states.count(TwinAgentState.SEATED),
            completed_orders=completed,
            abandoned_orders=abandoned,
            order_status_counts=status_counts(),
            agents=_frame_agents(
                scenario.store_id,
                active,
                order_ids,
                scenario.staff_count,
            ),
        ))

    def record(
        event_type: str,
        customer: DemandCustomer,
    ) -> None:
        nonlocal event_sequence
        event_sequence += 1
        states = list(active.values())
        events.append(OperationsSimulationEvent(
            sequence=event_sequence,
            at_minute=round(env.now, 3),
            event_type=event_type,
            customer_id=customer.customer_id,
            order_id=customer.order_id,
            queue_count=states.count(TwinAgentState.QUEUE),
            in_service_count=(
                states.count(TwinAgentState.ORDERING)
                + states.count(TwinAgentState.WAITING)
            ),
            completed_orders=completed,
            abandoned_orders=abandoned,
        ))
        snapshot(env.now)

    def customer_process(customer: DemandCustomer):
        nonlocal completed, abandoned, max_queue, busy_minutes, seat_busy_minutes
        active[customer.customer_id] = TwinAgentState.ENTERING
        order_ids[customer.customer_id] = customer.order_id
        record("customer_entered", customer)
        yield env.timeout(0.12)

        order_states[customer.order_id] = "waiting"
        active[customer.customer_id] = TwinAgentState.QUEUE
        record("order_received", customer)
        record("queued", customer)
        queue_started = env.now

        with staff.request() as request:
            max_queue = max(max_queue, len(staff.queue))
            outcome = yield request | env.timeout(customer.patience_minutes)
            if request not in outcome:
                abandoned += 1
                order_states[customer.order_id] = "abandoned"
                active[customer.customer_id] = TwinAgentState.EXITING
                record("abandoned", customer)
                yield env.timeout(0.22)
                active.pop(customer.customer_id, None)
                record("customer_exited", customer)
                return

            waits.append(env.now - queue_started)
            order_states[customer.order_id] = "preparing"
            active[customer.customer_id] = TwinAgentState.ORDERING
            busy_minutes += min(
                customer.service_minutes,
                max(scenario.duration_minutes - env.now, 0),
            )
            record("preparing", customer)
            ordering_minutes = min(0.45, customer.service_minutes)
            yield env.timeout(ordering_minutes)
            active[customer.customer_id] = TwinAgentState.WAITING
            snapshot(env.now)
            if customer.service_minutes > ordering_minutes:
                yield env.timeout(customer.service_minutes - ordering_minutes)

        order_states[customer.order_id] = "ready"
        record("ready", customer)
        yield env.timeout(PICKUP_MINUTES)
        completed += 1
        order_states[customer.order_id] = "completed"
        record("completed", customer)

        if customer.should_sit and seats.count < scenario.seat_count:
            with seats.request() as seat_request:
                yield seat_request
                active[customer.customer_id] = TwinAgentState.SEATED
                seat_busy_minutes += min(
                    customer.stay_minutes,
                    max(scenario.duration_minutes - env.now, 0),
                )
                record("seated", customer)
                yield env.timeout(customer.stay_minutes)
        active[customer.customer_id] = TwinAgentState.EXITING
        snapshot(env.now)
        yield env.timeout(0.22)
        active.pop(customer.customer_id, None)
        record("customer_exited", customer)

    def arrivals():
        previous_arrival = 0.0
        for customer in demand:
            yield env.timeout(max(customer.arrival_minute - previous_arrival, 0))
            previous_arrival = customer.arrival_minute
            env.process(customer_process(customer))

    def sampler():
        while env.now < scenario.duration_minutes:
            snapshot(env.now)
            yield env.timeout(SAMPLE_MINUTES)

    env.process(arrivals())
    env.process(sampler())
    env.run(until=scenario.duration_minutes)
    snapshot(scenario.duration_minutes)

    in_progress = sum(
        state in {"waiting", "preparing", "ready"}
        for state in order_states.values()
    )
    staff_capacity = scenario.staff_count * scenario.duration_minutes
    seat_capacity = scenario.seat_count * scenario.duration_minutes
    metrics = OperationsSimulationMetrics(
        visitors=len(demand),
        completed_orders=completed,
        abandoned_orders=abandoned,
        in_progress_orders=in_progress,
        average_wait_minutes=round(sum(waits) / len(waits), 2) if waits else 0,
        max_queue=max_queue,
        staff_utilization_percent=round(
            min(busy_minutes / staff_capacity * 100, 100),
            1,
        ),
        seat_utilization_percent=(
            round(min(seat_busy_minutes / seat_capacity * 100, 100), 1)
            if scenario.seat_count > 0
            else 0
        ),
    )
    return OperationsSimulationResult(
        run_id=_run_id(scenario, demand_trace_id),
        generated_at=datetime.now(timezone.utc),
        scenario=scenario,
        metrics=metrics,
        frames=frames,
        events=events,
        demand_trace_id=demand_trace_id,
        assumptions=[
            "시간대별 방문율을 따르는 구간별 포아송 도착 과정으로 생성했습니다.",
            "주문·제조 시간은 입력 평균을 따르는 로그정규분포로 생성했습니다.",
            "고객은 개인별 인내시간을 넘기면 주문을 포기합니다.",
            "결과는 What-if 전용이며 StoreState와 OrderEvent에 저장하지 않습니다.",
        ],
    )


def run_operations_simulation(
    scenario: OperationsSimulationScenario,
) -> OperationsSimulationResult:
    """기존 단일 시나리오 API를 유지하는 하위 호환 진입점."""
    profile = [OperationsArrivalProfileSegment(
        start_minute=0,
        end_minute=scenario.duration_minutes,
        arrivals_per_hour=scenario.arrivals_per_hour,
    )]
    demand, demand_trace_id = _generate_demand(
        profile,
        multiplier=scenario.event_multiplier,
        scenario=scenario,
    )
    return _run_with_demand(scenario, demand, demand_trace_id)


def run_operations_comparison(
    request: OperationsComparisonRequest,
) -> OperationsComparisonResult:
    profile = request.arrival_profile or _default_profile(
        request.duration_minutes,
        request.fallback_arrivals_per_hour,
    )
    weighted_rate = sum(
        segment.arrivals_per_hour * (segment.end_minute - segment.start_minute)
        for segment in profile
    ) / request.duration_minutes

    common = {
        "store_id": request.store_id,
        "duration_minutes": request.duration_minutes,
        "arrivals_per_hour": round(weighted_rate, 3),
        "average_service_minutes": request.average_service_minutes,
        "service_variability": request.service_variability,
        "patience_minutes": request.patience_minutes,
        "seat_count": request.seat_count,
        "dine_in_rate": request.dine_in_rate,
        "seed": request.seed,
    }
    normal_scenario = OperationsSimulationScenario(
        **common,
        name="평상시 · 직원 1명",
        staff_count=1,
        event_multiplier=1,
    )
    event_one_scenario = OperationsSimulationScenario(
        **common,
        name=f"행사 ×{request.event_multiplier:g} · 직원 1명",
        staff_count=1,
        event_multiplier=request.event_multiplier,
    )
    event_two_scenario = OperationsSimulationScenario(
        **common,
        name=f"행사 ×{request.event_multiplier:g} · 직원 2명",
        staff_count=2,
        event_multiplier=request.event_multiplier,
    )

    base_demand, base_trace_id = _generate_demand(
        profile,
        multiplier=1,
        scenario=normal_scenario,
    )
    event_demand, event_trace_id = _generate_demand(
        profile,
        multiplier=request.event_multiplier,
        scenario=event_one_scenario,
    )
    normal_full = _run_with_demand(normal_scenario, base_demand, base_trace_id)
    # 비교 화면에서 평상시는 기준 KPI만 사용한다. 좌우 재생 대상인 행사 두 조건에
    # 응답 용량을 집중하고, 단일 API에서는 여전히 전체 프레임을 받을 수 있다.
    normal_one = normal_full.model_copy(update={
        "frames": [normal_full.frames[0], normal_full.frames[-1]],
        "events": [],
    })
    event_one = _run_with_demand(event_one_scenario, event_demand, event_trace_id)
    event_two = _run_with_demand(event_two_scenario, event_demand, event_trace_id)

    return OperationsComparisonResult(
        comparison_id=_hash_payload("comparison", request.model_dump(mode="json")),
        generated_at=datetime.now(timezone.utc),
        demand_source=request.demand_source,
        demand_window_label=request.demand_window_label,
        arrival_profile=profile,
        base_trace_id=base_trace_id,
        event_demand_trace_id=event_trace_id,
        normal_one=normal_one,
        event_one=event_one,
        event_two=event_two,
    )
