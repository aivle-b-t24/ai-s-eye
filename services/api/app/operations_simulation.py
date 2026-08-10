"""본사 What-if 운영 비교용 결정적 이산사건 시뮬레이션.

실제 StoreState/OrderEvent 저장소에는 기록하지 않는다. 동일한 입력과 seed는
동일한 방문·서비스·이탈 흐름과 재생 프레임을 만든다.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import random

import simpy

from .models import (
    OperationsSimulationFrame,
    OperationsSimulationMetrics,
    OperationsSimulationResult,
    OperationsSimulationScenario,
    TwinAgent,
    TwinAgentRole,
    TwinAgentState,
)


SAMPLE_MINUTES = 2

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


def _run_id(scenario: OperationsSimulationScenario) -> str:
    encoded = json.dumps(
        scenario.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=True,
    ).encode()
    return f"sim-{hashlib.sha256(encoded).hexdigest()[:12]}"


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
                point = _position_with_jitter(base, max(index - len(layout["queue"]) + 1, 0))
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
                x=point[0],
                y=point[1],
                role=TwinAgentRole.CUSTOMER,
                state=state,
                zone=zone,
            ))
    return agents


def run_operations_simulation(
    scenario: OperationsSimulationScenario,
) -> OperationsSimulationResult:
    arrival_rng = random.Random(scenario.seed)
    env = simpy.Environment()
    staff = simpy.Resource(env, capacity=scenario.staff_count)
    seats = simpy.Resource(env, capacity=max(scenario.seat_count, 1))
    active: dict[str, TwinAgentState] = {}
    frames: list[OperationsSimulationFrame] = []
    waits: list[float] = []
    seat_samples: list[int] = []
    visitors = 0
    completed = 0
    abandoned = 0
    max_queue = 0
    busy_minutes = 0.0

    def snapshot(at_minute: float) -> None:
        states = list(active.values())
        frame = OperationsSimulationFrame(
            at_minute=round(at_minute, 2),
            queue_count=states.count(TwinAgentState.QUEUE),
            in_service_count=(
                states.count(TwinAgentState.ORDERING)
                + states.count(TwinAgentState.WAITING)
            ),
            seated_count=states.count(TwinAgentState.SEATED),
            completed_orders=completed,
            abandoned_orders=abandoned,
            agents=_frame_agents(scenario.store_id, active, scenario.staff_count),
        )
        if frames and frames[-1].at_minute == frame.at_minute:
            frames[-1] = frame
        else:
            frames.append(frame)
        seat_samples.append(frame.seated_count)

    def customer(customer_number: int):
        nonlocal completed, abandoned, max_queue, busy_minutes
        customer_id = f"sim-customer-{customer_number:04d}"
        customer_rng = random.Random(f"{scenario.seed}:{customer_number}")
        patience = scenario.patience_minutes * customer_rng.uniform(0.7, 1.3)
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
        service_minutes = max(service_minutes, 0.35)
        should_sit = (
            scenario.seat_count > 0
            and customer_rng.random() < scenario.dine_in_rate
        )
        stay_minutes = max(customer_rng.expovariate(1 / 20), 4)
        active[customer_id] = TwinAgentState.ENTERING
        yield env.timeout(0.12)
        active[customer_id] = TwinAgentState.QUEUE
        queue_started = env.now

        with staff.request() as request:
            max_queue = max(max_queue, len(staff.queue))
            outcome = yield request | env.timeout(patience)
            if request not in outcome:
                abandoned += 1
                active[customer_id] = TwinAgentState.EXITING
                yield env.timeout(0.22)
                active.pop(customer_id, None)
                return

            waits.append(env.now - queue_started)
            active[customer_id] = TwinAgentState.ORDERING
            busy_minutes += min(service_minutes, max(scenario.duration_minutes - env.now, 0))
            order_step = min(0.45, service_minutes)
            yield env.timeout(order_step)
            active[customer_id] = TwinAgentState.WAITING
            if service_minutes > order_step:
                yield env.timeout(service_minutes - order_step)

        completed += 1
        if should_sit and seats.count < scenario.seat_count:
            with seats.request() as seat_request:
                yield seat_request
                active[customer_id] = TwinAgentState.SEATED
                yield env.timeout(stay_minutes)
        active[customer_id] = TwinAgentState.EXITING
        yield env.timeout(0.22)
        active.pop(customer_id, None)

    def arrivals():
        nonlocal visitors
        effective_rate = scenario.arrivals_per_hour * scenario.event_multiplier
        while True:
            yield env.timeout(arrival_rng.expovariate(effective_rate / 60))
            if env.now >= scenario.duration_minutes:
                return
            visitors += 1
            env.process(customer(visitors))

    def sampler():
        while env.now < scenario.duration_minutes:
            snapshot(env.now)
            yield env.timeout(SAMPLE_MINUTES)

    env.process(arrivals())
    env.process(sampler())
    env.run(until=scenario.duration_minutes)
    snapshot(scenario.duration_minutes)

    in_progress = sum(
        state in {
            TwinAgentState.QUEUE,
            TwinAgentState.ORDERING,
            TwinAgentState.WAITING,
        }
        for state in active.values()
    )
    staff_capacity = scenario.staff_count * scenario.duration_minutes
    seat_capacity = scenario.seat_count * max(len(seat_samples), 1)
    metrics = OperationsSimulationMetrics(
        visitors=visitors,
        completed_orders=completed,
        abandoned_orders=abandoned,
        in_progress_orders=in_progress,
        average_wait_minutes=round(sum(waits) / len(waits), 2) if waits else 0,
        max_queue=max_queue,
        staff_utilization_percent=round(min(busy_minutes / staff_capacity * 100, 100), 1),
        seat_utilization_percent=(
            round(min(sum(seat_samples) / seat_capacity * 100, 100), 1)
            if scenario.seat_count > 0
            else 0
        ),
    )
    return OperationsSimulationResult(
        run_id=_run_id(scenario),
        generated_at=datetime.now(timezone.utc),
        scenario=scenario,
        metrics=metrics,
        frames=frames,
        assumptions=[
            "방문 간격은 포아송 도착 과정으로 생성했습니다.",
            "주문·제조 시간은 입력 평균을 따르는 로그정규분포로 생성했습니다.",
            "고객은 개인별 인내시간을 넘기면 주문을 포기합니다.",
            "결과는 What-if 전용이며 StoreState와 OrderEvent에 저장하지 않습니다.",
        ],
    )
