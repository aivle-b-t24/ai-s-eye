"""저장된 YOLO/ByteTrack 결과에 현재 직원 역할 정책을 다시 적용한다.

모델 추론은 바꾸지 않고 ROI 역할 규칙만 수정했을 때의 결과를 빠르게 비교하기
위한 도구다. ``evaluate_staff_role.py``가 만든 ``staff_role_seconds.json``을 입력한다.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cafe_stores import StaffPresenceState, StaffRoleState, staff_role_policy
from cafe_tracking import load_scene_cuts
from evaluate_staff_role import summarize


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SCENE_CUTS = SCRIPT_DIR / "cafe_scene_cuts.json"


def row_epoch(row: dict, cuts: dict[str, set[int]]) -> int:
    if row.get("tracking_epoch") is not None:
        return int(row["tracking_epoch"])
    camera_cuts = cuts.get(str(row["camera"]), set())
    return sum(int(row["segment"]) >= segment for segment in camera_cuts)


def replay_rows(rows: list[dict], cuts: dict[str, set[int]]) -> list[dict]:
    if not rows:
        return []
    store_id = rows[0]["store_id"]
    policy = staff_role_policy(store_id)
    roles = StaffRoleState(
        max_active_staff=policy.get("max_active_staff"),
        locked_bbox_overlap_threshold=policy.get(
            "locked_bbox_overlap_threshold"
        ),
        lock_grace_updates=policy.get("lock_grace_updates", 10),
    )
    presence = StaffPresenceState()
    last_epoch = None
    replayed = []
    for row in rows:
        epoch = row_epoch(row, cuts)
        if epoch != last_epoch:
            roles.reset()
            presence.reset()
            last_epoch = epoch
        details = row.get("configured_details") or row["hybrid_details"]
        evidences = [
            {
                "foot_inside": detail["foot_inside"],
                "overlap_ratio": detail["bbox_overlap"],
            }
            for detail in details
        ]
        flags = roles.update_evidence(
            evidences,
            [detail["track_id"] for detail in details],
            use_bbox=policy["use_bbox"],
            bbox_overlap_threshold=policy["bbox_overlap_threshold"],
        )
        positions = []
        for detail, is_staff in zip(details, flags):
            x1, y1, x2, y2 = detail["bbox"]
            positions.append(
                {
                    "track_id": detail["track_id"],
                    "x": (x1 + x2) / 2,
                    "y": y2,
                    "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                    "type": "staff" if is_staff else "customer",
                    "state": "working" if is_staff else "unknown",
                    "zone": "staff" if is_staff else None,
                }
            )
        resolved_positions, count = presence.update(positions)
        replayed.append(
            {
                **row,
                "tracking_epoch": epoch,
                "policy_raw_staff_count": int(sum(flags)),
                "policy_staff_count": count,
                "policy_staff_track_ids": [
                    position["track_id"]
                    for position in resolved_positions
                    if position.get("type") == "staff"
                ],
            }
        )
    return replayed


def continuity_summary(rows: list[dict]) -> dict:
    last_ids_by_epoch: dict[int, tuple] = {}
    role_id_changes = 0
    epochs = []
    for row in rows:
        epoch = int(row["tracking_epoch"])
        if not epochs or epochs[-1] != epoch:
            epochs.append(epoch)
        ids = tuple(sorted(str(value) for value in row["policy_staff_track_ids"]))
        if not ids:
            continue
        previous = last_ids_by_epoch.get(epoch)
        if previous is not None and previous != ids:
            role_id_changes += 1
        last_ids_by_epoch[epoch] = ids
    return {
        "tracking_epochs": epochs,
        "scene_reset_count": max(len(epochs) - 1, 0),
        "staff_role_id_changes_within_epoch": role_id_changes,
        "staff_icon_missing_seconds": sum(
            not row["policy_staff_track_ids"] for row in rows
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="저장된 직원 판정 결과 정책 재생")
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--scene-cuts", type=Path, default=DEFAULT_SCENE_CUTS)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample-every", type=int, default=5)
    args = parser.parse_args()
    cuts = load_scene_cuts(args.scene_cuts)
    reports = []
    all_replayed = []
    for source in args.inputs:
        rows = json.loads(source.read_text(encoding="utf-8"))
        replayed = replay_rows(rows, cuts)
        sampled = replayed[:: args.sample_every]
        reports.append(
            {
                "source": str(source),
                "store_id": replayed[0]["store_id"],
                "camera": replayed[0]["camera"],
                "start_seconds": replayed[0]["source_seconds"],
                "end_seconds": replayed[-1]["source_seconds"],
                "all_seconds": {
                    "raw": summarize(replayed, "policy_raw_staff_count"),
                    "smoothed": summarize(replayed, "policy_staff_count"),
                },
                "review_samples": {
                    "raw": summarize(sampled, "policy_raw_staff_count"),
                    "smoothed": summarize(sampled, "policy_staff_count"),
                },
                "continuity": continuity_summary(replayed),
            }
        )
        all_replayed.extend(replayed)
    result = {
        "definition": {
            "source": "저장된 동일 YOLO/ByteTrack 검출 결과",
            "policy": "매장별 ROI 다수결 + 직원 ID 고정 + 10초 가림 유지",
            "sample_every_seconds": args.sample_every,
        },
        "windows": reports,
        "all": {
            "raw": summarize(all_replayed, "policy_raw_staff_count"),
            "smoothed": summarize(all_replayed, "policy_staff_count"),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
