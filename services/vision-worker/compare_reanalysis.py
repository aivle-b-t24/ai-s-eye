"""이전 Vision JSON과 승인 ROI 재분석 JSON의 차이를 요약한다."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean


def load_states(path: Path) -> list[dict]:
    document = json.loads(path.read_text(encoding="utf-8"))
    states = document.get("states", document)
    if not isinstance(states, list):
        raise ValueError(f"states 배열을 찾을 수 없습니다: {path}")
    return states


def metrics(states: list[dict]) -> dict:
    positions = [
        position
        for state in states
        for position in state.get("positions", [])
    ]
    explicit_tracks = [
        position for position in positions if position.get("track_id") is not None
    ]
    explicit_states = [
        position
        for position in positions
        if position.get("state") not in {None, "unknown"}
    ]
    return {
        "state_count": len(states),
        "position_count": len(positions),
        "track_coverage": (
            len(explicit_tracks) / len(positions) if positions else 0.0
        ),
        "state_coverage": (
            len(explicit_states) / len(positions) if positions else 0.0
        ),
        "average_people": mean(
            state["visible_person_count"] for state in states
        ) if states else 0.0,
        "average_queue": mean(
            state["queue_count_estimate"] for state in states
        ) if states else 0.0,
        "average_staff": mean(
            state.get("zone_counts", {}).get("staff", 0)
            for state in states
        ) if states else 0.0,
        "frame_identity_coverage": (
            sum(
                bool(
                    state.get("frame_id")
                    and state.get("processed_at")
                    and state.get("model_version")
                    and state.get("roi_version")
                )
                for state in states
            ) / len(states)
            if states else 0.0
        ),
    }


def paired_differences(before: list[dict], after: list[dict]) -> dict:
    before_by_store: dict[str, list[dict]] = defaultdict(list)
    after_by_store: dict[str, list[dict]] = defaultdict(list)
    for state in before:
        before_by_store[state["store_id"]].append(state)
    for state in after:
        after_by_store[state["store_id"]].append(state)

    people_differences = []
    queue_differences = []
    for store_id in sorted(set(before_by_store) & set(after_by_store)):
        for old, new in zip(
            before_by_store[store_id],
            after_by_store[store_id],
        ):
            people_differences.append(
                abs(
                    old["visible_person_count"]
                    - new["visible_person_count"]
                )
            )
            queue_differences.append(
                abs(
                    old["queue_count_estimate"]
                    - new["queue_count_estimate"]
                )
            )
    return {
        "paired_count": len(people_differences),
        "people_mae": mean(people_differences) if people_differences else 0.0,
        "queue_mae": mean(queue_differences) if queue_differences else 0.0,
    }


def percentage(value: float) -> str:
    return f"{value * 100:.1f}%"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args()

    before = load_states(args.before)
    after = load_states(args.after)
    before_metrics = metrics(before)
    after_metrics = metrics(after)
    differences = paired_differences(before, after)

    print("# Vision 재분석 비교")
    print()
    print("| 항목 | 기존 | 재분석 |")
    print("|---|---:|---:|")
    for key, label in (
        ("state_count", "상태 수"),
        ("position_count", "사람 위치 수"),
        ("average_people", "평균 고객 수"),
        ("average_queue", "평균 대기 수"),
        ("average_staff", "평균 직원 수"),
    ):
        print(
            f"| {label} | {before_metrics[key]:.2f} | "
            f"{after_metrics[key]:.2f} |"
        )
    for key, label in (
        ("track_coverage", "명시적 track_id 비율"),
        ("state_coverage", "명시적 행동 상태 비율"),
        ("frame_identity_coverage", "프레임 신원 완성 비율"),
    ):
        print(
            f"| {label} | {percentage(before_metrics[key])} | "
            f"{percentage(after_metrics[key])} |"
        )
    print()
    print(
        f"동일 순번 {differences['paired_count']}건 비교: "
        f"고객 수 MAE {differences['people_mae']:.2f}, "
        f"대기 수 MAE {differences['queue_mae']:.2f}"
    )
    print()
    print(
        "주의: 이 값은 정답 라벨 대비 정확도가 아니라 기존 산출물과 새 산출물의 "
        "변화량이다. 탐지 정확도는 별도 라벨 데이터로 평가해야 한다."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
