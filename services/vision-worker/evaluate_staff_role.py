"""직원 ROI 판정을 수동 직원 수 라벨과 비교한다.

CAFE 원본은 사람 bbox와 identity만 제공하고 직원/고객 역할은 제공하지 않는다.
따라서 짧은 연속 구간의 실제 직원 수를 사람이 확인한 manifest를 사용한다.
동일한 YOLO·ByteTrack 결과에 `foot-only`와 현재의 `foot+bbox` 판정을 적용해
직원 수 exact accuracy, MAE, 과대/과소 집계를 비교한다.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from cafe_stores import (
    DETECTION_CONFIDENCE,
    StaffPresenceState,
    StaffRoleState,
    STORES,
    TRACKER_CONFIG,
    runtime_zones,
    staff_role_policy,
)
from cafe_tracking import (
    EXPECTED_MODEL_SHA256,
    iter_camera_frames,
    load_scene_cuts,
    reset_ultralytics_tracker,
    validate_model_file,
)
from roi_zone_counter import staff_zone_evidence


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_MANIFEST = SCRIPT_DIR / "staff_validation_windows.json"
DEFAULT_SCENE_CUTS = SCRIPT_DIR / "cafe_scene_cuts.json"
DEFAULT_OUTPUT = SCRIPT_DIR / "outputs" / "staff_validation"


@dataclass(frozen=True)
class Window:
    id: str
    camera: str
    store_id: str
    start_seconds: float
    duration_seconds: float
    expected_staff_count: int
    review_note: str

    @property
    def end_seconds(self) -> float:
        return self.start_seconds + self.duration_seconds


class StaffVoteState:
    """프로덕션과 같은 최근 5회 중 3회 다수결을 판정 방식별로 적용한다."""

    def __init__(
        self,
        mode: str,
        window_size: int = 5,
        required_votes: int = 3,
        overlap_threshold: float = 0.30,
    ):
        if mode not in {"foot-only", "foot+bbox"}:
            raise ValueError(f"지원하지 않는 직원 판정 방식: {mode}")
        self.mode = mode
        self.window_size = window_size
        self.required_votes = required_votes
        self.overlap_threshold = overlap_threshold
        self.history: dict[int | str, collections.deque] = {}

    def reset(self) -> None:
        self.history.clear()

    def update(self, boxes, track_ids, zones) -> tuple[list[bool], list[dict]]:
        flags = []
        details = []
        for box, track_id in zip(boxes, track_ids):
            evidence = staff_zone_evidence(
                box,
                zones,
                overlap_threshold=self.overlap_threshold,
            )
            candidate = bool(
                evidence["foot_inside"]
                if self.mode == "foot-only"
                else evidence["candidate"]
            )
            if track_id is None:
                is_staff = candidate
                votes = int(candidate)
                observations = 1
            else:
                history = self.history.setdefault(
                    track_id,
                    collections.deque(maxlen=self.window_size),
                )
                history.append(candidate)
                votes = sum(history)
                observations = len(history)
                is_staff = votes >= self.required_votes
            flags.append(is_staff)
            details.append(
                {
                    "track_id": track_id,
                    "staff": bool(is_staff),
                    "candidate": candidate,
                    "votes": int(votes),
                    "observations": observations,
                    "foot_inside": bool(evidence["foot_inside"]),
                    "bbox_overlap": round(float(evidence["overlap_ratio"]), 4),
                    "bbox": [round(float(value), 2) for value in box],
                }
            )
        return flags, details


def read_image(path: Path):
    return cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)


def load_manifest(path: Path) -> tuple[list[Window], float]:
    document = json.loads(path.read_text(encoding="utf-8"))
    sample_every = float(document["sample_every_seconds"])
    if sample_every <= 0:
        raise ValueError("sample_every_seconds는 0보다 커야 합니다")
    windows = [Window(**item) for item in document["windows"]]
    if len({window.id for window in windows}) != len(windows):
        raise ValueError("직원 검증 window id가 중복되었습니다")
    return windows, sample_every


def should_review(source_seconds: float, window: Window, sample_every: float) -> bool:
    if not window.start_seconds <= source_seconds < window.end_seconds:
        return False
    offset = source_seconds - window.start_seconds
    nearest = round(offset / sample_every) * sample_every
    return abs(offset - nearest) <= 0.11


def summarize(rows: list[dict], key: str) -> dict:
    expected = np.asarray([row["expected_staff_count"] for row in rows], dtype=float)
    predicted = np.asarray([row[key] for row in rows], dtype=float)
    differences = predicted - expected
    true_positive = np.minimum(predicted, expected).sum()
    false_positive = np.maximum(differences, 0).sum()
    false_negative = np.maximum(-differences, 0).sum()
    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
    return {
        "samples": len(rows),
        "exact_accuracy_percent": round(float(np.mean(differences == 0) * 100), 3),
        "count_mae": round(float(np.mean(np.abs(differences))), 6),
        "under_count_samples": int(np.sum(differences < 0)),
        "over_count_samples": int(np.sum(differences > 0)),
        "count_level_precision_percent": round(float(precision * 100), 3),
        "count_level_recall_percent": round(float(recall * 100), 3),
    }


def draw_audit_frame(image: np.ndarray, row: dict) -> np.ndarray:
    result = image.copy()
    for detail in row["configured_details"]:
        x1, y1, x2, y2 = map(int, detail["bbox"])
        color = (20, 20, 240) if detail["staff"] else (40, 190, 40)
        cv2.rectangle(result, (x1, y1), (x2, y2), color, 3 if detail["staff"] else 1)
        label = (
            f"id={detail['track_id']} staff={int(detail['staff'])} "
            f"foot={int(detail['foot_inside'])} overlap={detail['bbox_overlap']:.2f}"
        )
        cv2.putText(
            result,
            label,
            (x1, max(y1 - 6, 18)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            color,
            2,
            cv2.LINE_AA,
        )
    title = (
        f"{row['window_id']} {row['source_seconds']:.1f}s "
        f"GT={row['expected_staff_count']} foot={row['foot_only_count']} "
        f"hybrid={row['hybrid_count']} configured={row['configured_count']} "
        f"smoothed={row['configured_smoothed_count']}"
    )
    cv2.rectangle(result, (0, 0), (result.shape[1], 36), (0, 0, 0), -1)
    cv2.putText(
        result,
        title,
        (8, 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return result


def write_contact_sheets(items: list[tuple[dict, np.ndarray]], output: Path) -> list[str]:
    if not items:
        return []
    paths = []
    per_sheet = 20
    tile_width, tile_height = 480, 270
    for page, start in enumerate(range(0, len(items), per_sheet), 1):
        sheet = np.zeros((tile_height * 4, tile_width * 5, 3), dtype=np.uint8)
        for index, (row, image) in enumerate(items[start : start + per_sheet]):
            panel = cv2.resize(draw_audit_frame(image, row), (tile_width, tile_height))
            y, x = divmod(index, 5)
            sheet[y * tile_height : (y + 1) * tile_height, x * tile_width : (x + 1) * tile_width] = panel
        path = output / f"review_{items[0][0]['camera']}_{page:02d}.jpg"
        cv2.imwrite(str(path), sheet)
        paths.append(str(path))
    return paths


def evaluate_window(
    *,
    window: Window,
    sample_every: float,
    cafe_root: Path,
    model_path: Path,
    cuts: set[int],
) -> tuple[list[dict], list[dict], list[tuple[dict, np.ndarray]]]:
    model = YOLO(model_path)
    foot_state = StaffVoteState("foot-only")
    hybrid_state = StaffVoteState("foot+bbox")
    policy = staff_role_policy(window.store_id)
    configured_state = StaffVoteState(
        "foot+bbox" if policy["use_bbox"] else "foot-only",
        overlap_threshold=policy["bbox_overlap_threshold"],
    )
    configured_roles = StaffRoleState(
        max_active_staff=policy.get("max_active_staff"),
        locked_bbox_overlap_threshold=policy.get(
            "locked_bbox_overlap_threshold"
        ),
        lock_grace_updates=policy.get("lock_grace_updates", 10),
    )
    configured_presence = StaffPresenceState()
    rows = []
    second_rows = []
    audit_images = []
    camera_id = f"{window.store_id}-cam1"
    next_vote = window.start_seconds
    tracking_epoch = -1

    for sample in iter_camera_frames(cafe_root, window.camera, scene_cuts=cuts):
        if sample.source_seconds >= window.end_seconds:
            break
        if sample.reset_before:
            reset_ultralytics_tracker(model)
            foot_state.reset()
            hybrid_state.reset()
            configured_state.reset()
            configured_roles.reset()
            configured_presence.reset()
            tracking_epoch += 1
        image = read_image(sample.path)
        if image is None:
            continue
        result = model.track(
            image,
            persist=True,
            tracker=TRACKER_CONFIG,
            classes=[0],
            conf=DETECTION_CONFIDENCE,
            iou=0.5,
            agnostic_nms=True,
            verbose=False,
        )[0]
        boxes = (
            result.boxes.xyxy.cpu().numpy()
            if result.boxes is not None
            else np.empty((0, 4))
        )
        track_ids = (
            result.boxes.id.cpu().numpy().astype(int).tolist()
            if result.boxes is not None and result.boxes.id is not None
            else [None] * len(boxes)
        )
        # 프로덕션은 약 5fps 전체를 ByteTrack에 넣고 직원 역할 투표는 1초 출력마다
        # 갱신한다. 수동 라벨과 비교하는 표본만 manifest 간격(기본 5초)으로 줄인다.
        if sample.source_seconds + 0.11 < next_vote:
            continue
        zones = runtime_zones(window.store_id, camera_id, image.shape[1], image.shape[0])
        foot_flags, foot_details = foot_state.update(boxes, track_ids, zones)
        hybrid_flags, hybrid_details = hybrid_state.update(boxes, track_ids, zones)
        _, configured_details = configured_state.update(
            boxes, track_ids, zones
        )
        configured_flags = configured_roles.update(
            boxes,
            track_ids,
            zones,
            use_bbox=policy["use_bbox"],
            bbox_overlap_threshold=policy["bbox_overlap_threshold"],
        )
        for detail, is_staff in zip(configured_details, configured_flags):
            detail["staff"] = bool(is_staff)
        configured_count = int(sum(configured_flags))
        configured_positions = []
        for detail, is_staff in zip(configured_details, configured_flags):
            x1, y1, x2, y2 = detail["bbox"]
            configured_positions.append({
                "track_id": detail["track_id"],
                "x": (x1 + x2) / 2,
                "y": y2,
                "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                "type": "staff" if is_staff else "customer",
                "state": "working" if is_staff else "unknown",
                "zone": "staff" if is_staff else None,
            })
        _, configured_smoothed_count = configured_presence.update(
            configured_positions
        )
        vote_second = next_vote
        next_vote += 1.0
        row = {
            "window_id": window.id,
            "camera": window.camera,
            "store_id": window.store_id,
            "segment": sample.segment,
            "frame_number": sample.frame_number,
            "source_seconds": round(sample.source_seconds, 3),
            "tracking_epoch": tracking_epoch,
            "expected_staff_count": window.expected_staff_count,
            "foot_only_count": int(sum(foot_flags)),
            "hybrid_count": int(sum(hybrid_flags)),
            "configured_count": configured_count,
            "configured_smoothed_count": configured_smoothed_count,
            "foot_details": foot_details,
            "hybrid_details": hybrid_details,
            "configured_details": configured_details,
        }
        second_rows.append(row)
        if not should_review(vote_second, window, sample_every):
            continue
        rows.append(row)
        audit_images.append((row, image))
        print(
            f"  {window.id}: {sample.source_seconds:6.1f}s "
            f"GT={window.expected_staff_count} foot={sum(foot_flags)} "
            f"hybrid={sum(hybrid_flags)} configured={configured_count} "
            f"smoothed={configured_smoothed_count}"
        )
    return rows, second_rows, audit_images


def write_results(
    rows: list[dict], second_rows: list[dict], output: Path, manifest: Path
) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    by_camera = {}
    for camera in sorted({row["camera"] for row in rows}):
        selected = [row for row in rows if row["camera"] == camera]
        by_camera[camera] = {
            "foot_only": summarize(selected, "foot_only_count"),
            "foot_bbox": summarize(selected, "hybrid_count"),
            "configured": summarize(selected, "configured_count"),
            "configured_smoothed": summarize(
                selected, "configured_smoothed_count"
            ),
        }
    report = {
        "definition": {
            "ground_truth": "원본 CCTV를 사람이 확인한 표본별 실제 직원 수",
            "comparison": "동일 YOLO/ByteTrack 결과에서 발 좌표만 vs 발 또는 bbox 중첩",
            "voting": "각 방식 모두 최근 5개 표본 중 3개 이상",
            "metric_scope": "직원 수 기준이며, 사람별 역할 Precision/Recall은 아님",
            "manifest": str(manifest),
        },
        "all": {
            "foot_only": summarize(rows, "foot_only_count"),
            "foot_bbox": summarize(rows, "hybrid_count"),
            "configured": summarize(rows, "configured_count"),
            "configured_smoothed": summarize(
                rows, "configured_smoothed_count"
            ),
        },
        "by_camera": by_camera,
    }
    (output / "staff_role_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "staff_role_samples.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "staff_role_seconds.json").write_text(
        json.dumps(second_rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (output / "staff_role_samples.csv").open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(
            target,
            fieldnames=[
                "window_id",
                "camera",
                "store_id",
                "segment",
                "frame_number",
                "source_seconds",
                "expected_staff_count",
                "foot_only_count",
                "hybrid_count",
                "configured_count",
                "configured_smoothed_count",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in writer.fieldnames})
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="직원 ROI 수동 표본 A/B 검증")
    parser.add_argument("--cafe-root", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--camera", choices=("5", "21"), default=None)
    args = parser.parse_args()
    validate_model_file(args.model, EXPECTED_MODEL_SHA256)
    windows, sample_every = load_manifest(args.manifest)
    if args.camera:
        windows = [window for window in windows if window.camera == args.camera]
    cuts = load_scene_cuts(DEFAULT_SCENE_CUTS)
    args.output.mkdir(parents=True, exist_ok=True)
    all_rows = []
    all_second_rows = []
    sheets = []
    for window in windows:
        rows, second_rows, images = evaluate_window(
            window=window,
            sample_every=sample_every,
            cafe_root=args.cafe_root,
            model_path=args.model,
            cuts=cuts.get(window.camera, set()),
        )
        all_rows.extend(rows)
        all_second_rows.extend(second_rows)
        sheets.extend(write_contact_sheets(images, args.output))
    report = write_results(all_rows, all_second_rows, args.output, args.manifest)
    print(json.dumps({**report, "review_sheets": sheets}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
