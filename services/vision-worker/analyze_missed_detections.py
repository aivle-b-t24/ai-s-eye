"""고정 MOT test 구간의 YOLO 미탐지 원인을 활동/가림/카메라별로 분석한다."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment

from benchmark_tracking import read_image, recover_image_from_zip
from cafe_tracking import load_scene_cuts
from evaluate_mot_tracking import (
    DEFAULT_MANIFEST,
    DEFAULT_SCENE_CUTS,
    build_labeled_frames,
    box_iou_matrix,
    load_identity_ground_truth,
    load_predictions,
    load_windows,
    materialize_windows,
    normalized_gt_rows,
    pixel_boxes,
)


SCRIPT_DIR = Path(__file__).resolve().parent
SEATED_ACTIVITIES = {"Working/Studying", "Eating/Drinking"}


def activity_map(annotation_path: Path) -> dict[int, str]:
    if not annotation_path.is_file():
        return {}
    annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
    result = {}
    for figure in annotation.get("figures", []):
        activities = [
            attribute.get("value", {}).get("key")
            for attribute in figure.get("attributes", [])
        ]
        activity = next((value for value in activities if value), "unknown")
        result[int(figure["id"])] = activity
    return result


def occlusion_coverage(boxes: np.ndarray) -> np.ndarray:
    """각 GT가 다른 GT에 가려진 면적 비율의 최댓값을 반환한다."""
    if len(boxes) < 2:
        return np.zeros(len(boxes), dtype=np.float64)
    top_left = np.maximum(boxes[:, None, :2], boxes[None, :, :2])
    bottom_right = np.minimum(boxes[:, None, 2:], boxes[None, :, 2:])
    size = np.maximum(bottom_right - top_left, 0)
    intersection = size[:, :, 0] * size[:, :, 1]
    np.fill_diagonal(intersection, 0)
    area = np.prod(np.maximum(boxes[:, 2:] - boxes[:, :2], 0), axis=1)
    coverage = np.divide(
        intersection,
        area[:, None],
        out=np.zeros_like(intersection),
        where=area[:, None] > 0,
    )
    return coverage.max(axis=1)


def metric_bucket() -> dict:
    return {"gt": 0, "matched": 0, "missed": 0}


def add_metric(bucket: dict, matched: bool) -> None:
    bucket["gt"] += 1
    bucket["matched"] += int(matched)
    bucket["missed"] += int(not matched)


def finalize_metric(bucket: dict) -> dict:
    return {
        **bucket,
        "recall_iou50": round(bucket["matched"] / max(bucket["gt"], 1) * 100, 3),
    }


def annotate_miss_frame(image: np.ndarray, gt_boxes: np.ndarray, missed: set[int], predicted) -> np.ndarray:
    panel = cv2.resize(image, (480, 270))
    sx, sy = 480 / image.shape[1], 270 / image.shape[0]
    for box in predicted["boxes"]:
        x1, y1, x2, y2 = map(int, (box[0] * sx, box[1] * sy, box[2] * sx, box[3] * sy))
        cv2.rectangle(panel, (x1, y1), (x2, y2), (255, 150, 40), 1)
    for index, box in enumerate(gt_boxes):
        x1, y1, x2, y2 = map(int, (box[0] * sx, box[1] * sy, box[2] * sx, box[3] * sy))
        color = (30, 30, 255) if index in missed else (40, 210, 40)
        cv2.rectangle(panel, (x1, y1), (x2, y2), color, 2 if index in missed else 1)
        if index in missed:
            cv2.putText(panel, "MISS", (x1, max(y1 - 3, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
    return panel


def analyze(
    cafe_root: Path,
    gt_zip: Path,
    prediction_path: Path,
    output: Path,
) -> dict:
    windows = load_windows(DEFAULT_MANIFEST)
    test_windows = [window for window in windows if window.split == "test"]
    ground_truth = load_identity_ground_truth(gt_zip)
    cuts = load_scene_cuts(DEFAULT_SCENE_CUTS)
    frames_by_camera = {
        camera: build_labeled_frames(cafe_root, camera, ground_truth, cuts.get(camera, set()))
        for camera in ("5", "21")
    }
    materialized = materialize_windows(test_windows, frames_by_camera)
    predictions = load_predictions(prediction_path)
    buckets = {
        "all": metric_bucket(),
        "by_camera": defaultdict(metric_bucket),
        "by_category": defaultdict(metric_bucket),
        "by_activity": defaultdict(metric_bucket),
        "seated": metric_bucket(),
        "not_seated": metric_bucket(),
        "occluded": metric_bucket(),
        "not_occluded": metric_bucket(),
    }
    box_heights = {"matched": [], "missed": []}
    miss_frames = []
    annotation_cache = {}

    for sequence, frames in materialized.items():
        camera = sequence.split("-")[0].replace("cam", "")
        category = "scene_cut" if "-cut-" in sequence else "crowded_occluded" if "-crowd-" in sequence else "normal"
        for frame_index, (frame, predicted) in enumerate(zip(frames, predictions[sequence]), 1):
            rows = normalized_gt_rows(ground_truth, camera, frame.source)
            gt_boxes = pixel_boxes(frame.boxes, predicted["width"], predicted["height"])
            predicted_boxes = np.asarray(predicted["boxes"], dtype=np.float64).reshape(-1, 4)
            ious = box_iou_matrix(gt_boxes, predicted_boxes)
            matched_gt = set()
            if len(gt_boxes) and len(predicted_boxes):
                gt_indexes, prediction_indexes = linear_sum_assignment(1 - ious)
                matched_gt = {
                    int(gt_index)
                    for gt_index, prediction_index in zip(gt_indexes, prediction_indexes)
                    if ious[gt_index, prediction_index] >= 0.5
                }
            coverage = occlusion_coverage(gt_boxes)
            annotation_path = frame.source.path.parent.parent / "ann.json"
            activities = annotation_cache.setdefault(annotation_path, activity_map(annotation_path))
            missed_indexes = set(range(len(gt_boxes))) - matched_gt
            for index, (row, box) in enumerate(zip(rows, gt_boxes)):
                matched = index in matched_gt
                activity = activities.get(int(row[0]), "unknown")
                seated = activity in SEATED_ACTIVITIES
                occluded = coverage[index] >= 0.15
                for bucket in (
                    buckets["all"],
                    buckets["by_camera"][camera],
                    buckets["by_category"][category],
                    buckets["by_activity"][activity],
                    buckets["seated" if seated else "not_seated"],
                    buckets["occluded" if occluded else "not_occluded"],
                ):
                    add_metric(bucket, matched)
                box_heights["matched" if matched else "missed"].append(float(box[3] - box[1]))
            if missed_indexes:
                image = read_image(frame.source.path)
                if image is None:
                    image = recover_image_from_zip(gt_zip, cafe_root, frame.source.path)
                miss_frames.append(
                    {
                        "sequence": sequence,
                        "frame_index": frame_index,
                        "miss_count": len(missed_indexes),
                        "image": image,
                        "gt_boxes": gt_boxes,
                        "missed": missed_indexes,
                        "predicted": predicted,
                    }
                )

    result = {
        "definition": {
            "matched": "Hungarian assignment with bbox IoU >= 0.50",
            "occluded": "another GT box covers at least 15% of this GT box",
            "seated_activities": sorted(SEATED_ACTIVITIES),
        },
        "all": finalize_metric(buckets["all"]),
        "by_camera": {key: finalize_metric(value) for key, value in buckets["by_camera"].items()},
        "by_category": {key: finalize_metric(value) for key, value in buckets["by_category"].items()},
        "by_activity": {key: finalize_metric(value) for key, value in buckets["by_activity"].items()},
        "seated": finalize_metric(buckets["seated"]),
        "not_seated": finalize_metric(buckets["not_seated"]),
        "occluded": finalize_metric(buckets["occluded"]),
        "not_occluded": finalize_metric(buckets["not_occluded"]),
        "bbox_height_pixels": {
            key: {
                "median": round(float(np.median(values)), 3),
                "p25": round(float(np.percentile(values, 25)), 3),
                "p75": round(float(np.percentile(values, 75)), 3),
            }
            for key, values in box_heights.items()
            if values
        },
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "detection_miss_analysis.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    for camera in ("5", "21"):
        selected = sorted(
            (item for item in miss_frames if item["sequence"].startswith(f"cam{camera}-")),
            key=lambda item: (-item["miss_count"], item["sequence"], item["frame_index"]),
        )[:12]
        sheet = np.zeros((810, 1920, 3), dtype=np.uint8)
        for index, item in enumerate(selected):
            row, column = divmod(index, 4)
            panel = annotate_miss_frame(
                item["image"], item["gt_boxes"], item["missed"], item["predicted"]
            )
            cv2.rectangle(panel, (0, 0), (480, 22), (0, 0, 0), -1)
            cv2.putText(
                panel,
                f"{item['sequence']} f{item['frame_index']} miss={item['miss_count']}",
                (5, 15),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
            y, x = row * 270, column * 480
            sheet[y : y + 270, x : x + 480] = panel
        cv2.imwrite(str(output / f"detection_misses_cam{camera}.jpg"), sheet)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="CAFE held-out detector miss analysis")
    parser.add_argument("--cafe-root", type=Path, required=True)
    parser.add_argument("--gt-zip", type=Path, required=True)
    parser.add_argument(
        "--predictions",
        type=Path,
        default=SCRIPT_DIR / "outputs" / "mot_validation" / "predictions" / "test" / "baseline-reset.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=SCRIPT_DIR / "outputs" / "mot_validation" / "miss_analysis",
    )
    args = parser.parse_args()
    print(json.dumps(analyze(args.cafe_root, args.gt_zip, args.predictions, args.output), indent=2))


if __name__ == "__main__":
    main()
