"""동일 CAFE 영상·가중치로 기존/개선 추적을 재현 가능한 방식으로 비교한다."""

from __future__ import annotations

import argparse
import json
import os
import time
import zipfile
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from cafe_tracking import (
    EXPECTED_MODEL_SHA256,
    TrackingEpoch,
    iter_camera_frames,
    load_scene_cuts,
    reset_ultralytics_tracker,
    validate_model_file,
)


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SCENE_CUTS = SCRIPT_DIR / "cafe_scene_cuts.json"
DEFAULT_TRACKER = SCRIPT_DIR / "trackers" / "bytetrack_cafe.yaml"
GT_MEMBER = "Cafe_Dataset/evaluation/gt_tracks.txt"


def read_image(path: Path):
    return cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)


def recover_image_from_zip(zip_path: Path, cafe_root: Path, path: Path):
    if not zip_path.is_file():
        return None
    relative = path.relative_to(cafe_root).as_posix()
    member = f"Cafe_Dataset/Dataset/cafe/{relative}"
    try:
        with zipfile.ZipFile(zip_path) as archive:
            encoded = np.frombuffer(archive.read(member), dtype=np.uint8)
    except (KeyError, zipfile.BadZipFile):
        return None
    return cv2.imdecode(encoded, cv2.IMREAD_COLOR)


def box_iou(first, second) -> float:
    left = max(float(first[0]), float(second[0]))
    top = max(float(first[1]), float(second[1]))
    right = min(float(first[2]), float(second[2]))
    bottom = min(float(first[3]), float(second[3]))
    intersection = max(right - left, 0.0) * max(bottom - top, 0.0)
    first_area = max(float(first[2] - first[0]), 0.0) * max(float(first[3] - first[1]), 0.0)
    second_area = max(float(second[2] - second[0]), 0.0) * max(float(second[3] - second[1]), 0.0)
    union = first_area + second_area - intersection
    return intersection / union if union > 0 else 0.0


def greedy_iou_matches(first_boxes, second_boxes, threshold: float = 0.5):
    candidates = sorted(
        (
            (box_iou(first, second), first_index, second_index)
            for first_index, first in enumerate(first_boxes)
            for second_index, second in enumerate(second_boxes)
        ),
        reverse=True,
    )
    used_first = set()
    used_second = set()
    matches = []
    for overlap, first_index, second_index in candidates:
        if overlap < threshold:
            break
        if first_index in used_first or second_index in used_second:
            continue
        used_first.add(first_index)
        used_second.add(second_index)
        matches.append((first_index, second_index))
    return matches


def greedy_foot_matches(first_boxes, second_boxes, max_distance: float = 60.0):
    def foot(box):
        return ((float(box[0]) + float(box[2])) / 2, float(box[3]))

    candidates = []
    for first_index, first in enumerate(first_boxes):
        first_foot = foot(first)
        for second_index, second in enumerate(second_boxes):
            second_foot = foot(second)
            distance = float(np.hypot(first_foot[0] - second_foot[0], first_foot[1] - second_foot[1]))
            if distance <= max_distance:
                candidates.append((distance, first_index, second_index))
    used_first = set()
    used_second = set()
    matches = []
    for _, first_index, second_index in sorted(candidates):
        if first_index in used_first or second_index in used_second:
            continue
        used_first.add(first_index)
        used_second.add(second_index)
        matches.append((first_index, second_index))
    return matches


def load_ground_truth(zip_path: Path, cameras: set[int]):
    ground_truth = {}
    if not zip_path.is_file():
        return ground_truth
    with zipfile.ZipFile(zip_path) as archive, archive.open(GT_MEMBER) as source:
        for raw_line in source:
            values = raw_line.split()
            camera = int(values[0])
            if camera not in cameras:
                continue
            segment = int(values[1])
            frame = int(values[2])
            box = tuple(float(value) for value in values[3:7])
            ground_truth.setdefault((str(camera), segment, frame), []).append(box)
    return ground_truth


def evaluate_variant(
    *,
    name: str,
    cafe_root: Path,
    model_path: Path,
    clip: str,
    cuts: set[int],
    ground_truth: dict,
    improved: bool,
    improved_tracker: Path = DEFAULT_TRACKER,
    segment_limit: int | None = None,
    source_zip: Path | None = None,
) -> dict:
    model = YOLO(model_path)
    tracker = str(improved_tracker) if improved else "bytetrack.yaml"
    confidence = 0.10 if improved else 0.30
    epoch = TrackingEpoch(f"camera-{clip}")
    epoch.reset()
    previous_boxes = np.empty((0, 4))
    previous_ids = []
    true_positive = false_positive = false_negative = 0
    count_error = evaluated_frames = 0
    continuity_matches = continuity_breaks = 0
    cut_pairs = cut_reused_ids = cut_possible_ids = 0
    processed_frames = 0
    source_frames = 0
    recovered_frames = 0
    decode_failures = []
    started = time.perf_counter()

    for sample in iter_camera_frames(
        cafe_root,
        clip,
        scene_cuts=cuts,
        segment_limit=segment_limit,
    ):
        source_frames += 1
        discontinuity = sample.reset_before and sample.reset_reason != "initial"
        if improved and discontinuity:
            reset_ultralytics_tracker(model)
            epoch.reset()
        image = read_image(sample.path)
        if image is None and source_zip is not None:
            image = recover_image_from_zip(source_zip, cafe_root, sample.path)
            if image is not None:
                recovered_frames += 1
        if image is None:
            decode_failures.append(str(sample.path))
            continue
        result = model.track(
            image,
            persist=True,
            tracker=tracker,
            classes=[0],
            conf=confidence,
            iou=0.5,
            agnostic_nms=True,
            verbose=False,
        )[0]
        boxes = result.boxes.xyxy.cpu().numpy() if result.boxes is not None else np.empty((0, 4))
        local_ids = (
            result.boxes.id.cpu().numpy().astype(int).tolist()
            if result.boxes is not None and result.boxes.id is not None
            else [None] * len(boxes)
        )
        public_ids = [
            epoch.public_id(track_id) if improved and track_id is not None else str(track_id)
            if track_id is not None else None
            for track_id in local_ids
        ]

        if processed_frames and discontinuity:
            previous_set = {track_id for track_id in previous_ids if track_id is not None}
            current_set = {track_id for track_id in public_ids if track_id is not None}
            cut_pairs += 1
            cut_reused_ids += len(previous_set & current_set)
            cut_possible_ids += min(len(previous_set), len(current_set))
        elif processed_frames:
            for previous_index, current_index in greedy_foot_matches(previous_boxes, boxes):
                previous_id = previous_ids[previous_index]
                current_id = public_ids[current_index]
                if previous_id is None or current_id is None:
                    continue
                continuity_matches += 1
                continuity_breaks += previous_id != current_id

        gt_boxes = ground_truth.get((clip, sample.segment, sample.frame_number))
        if gt_boxes is not None:
            height, width = image.shape[:2]
            scaled_gt = [
                (
                    box[0] * width / 1280,
                    box[1] * height / 720,
                    box[2] * width / 1280,
                    box[3] * height / 720,
                )
                for box in gt_boxes
            ]
            matches = greedy_iou_matches(boxes, scaled_gt)
            true_positive += len(matches)
            false_positive += len(boxes) - len(matches)
            false_negative += len(scaled_gt) - len(matches)
            count_error += abs(len(boxes) - len(scaled_gt))
            evaluated_frames += 1

        previous_boxes = boxes
        previous_ids = public_ids
        processed_frames += 1
        if processed_frames % 1000 == 0:
            print(f"  {name} camera {clip}: {processed_frames} frames")

    elapsed = time.perf_counter() - started
    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
    return {
        "variant": name,
        "camera": clip,
        "source_frames": source_frames,
        "frames": processed_frames,
        "recovered_from_zip": recovered_frames,
        "decode_failures": decode_failures,
        "elapsed_seconds": round(elapsed, 3),
        "throughput_fps": round(processed_frames / max(elapsed, 1e-9), 3),
        "detection": {
            "evaluated_frames": evaluated_frames,
            "precision_iou50": round(precision, 6),
            "recall_iou50": round(recall, 6),
            "f1_iou50": round(2 * precision * recall / max(precision + recall, 1e-9), 6),
            "count_mae": round(count_error / max(evaluated_frames, 1), 6),
        },
        "tracking_proxy": {
            "normal_matches": continuity_matches,
            "id_breaks": continuity_breaks,
            "id_break_rate": round(continuity_breaks / max(continuity_matches, 1), 6),
            "cut_pairs": cut_pairs,
            "cut_reused_ids": cut_reused_ids,
            "cut_possible_ids": cut_possible_ids,
            "cut_reuse_rate": round(cut_reused_ids / max(cut_possible_ids, 1), 6),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="CAFE ByteTrack 기존/개선 A/B 벤치마크")
    parser.add_argument("--cafe-root", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--gt-zip", type=Path, default=Path(os.getenv("AISEYE_CAFE_ZIP", "")))
    parser.add_argument("--cameras", nargs="+", default=["5", "21"])
    parser.add_argument("--limit", type=int, default=None, help="카메라별 앞 N세그먼트")
    parser.add_argument(
        "--improved-tracker",
        type=Path,
        default=DEFAULT_TRACKER,
        help="개선안에서 사용할 ByteTrack YAML",
    )
    parser.add_argument(
        "--variant",
        choices=("baseline", "improved", "both"),
        default="both",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=SCRIPT_DIR / "outputs" / "benchmarks" / "tracking_ab.json",
    )
    args = parser.parse_args()

    model_sha = validate_model_file(args.model, EXPECTED_MODEL_SHA256)
    cuts_by_camera = load_scene_cuts(DEFAULT_SCENE_CUTS)
    ground_truth = load_ground_truth(args.gt_zip, {int(camera) for camera in args.cameras})
    variants = (
        [("baseline", False), ("improved", True)]
        if args.variant == "both"
        else [(args.variant, args.variant == "improved")]
    )
    results = []
    for name, improved in variants:
        for clip in args.cameras:
            results.append(
                evaluate_variant(
                    name=name,
                    cafe_root=args.cafe_root,
                    model_path=args.model,
                    clip=str(clip),
                    cuts=cuts_by_camera.get(str(clip), set()),
                    ground_truth=ground_truth,
                    improved=improved,
                    improved_tracker=args.improved_tracker,
                    segment_limit=args.limit,
                    source_zip=args.gt_zip,
                )
            )

    report = {
        "schema_version": "1.0",
        "model_sha256": model_sha,
        "scene_cut_manifest": str(DEFAULT_SCENE_CUTS),
        "discontinuity_policy": "reset_verified_scene_cuts_and_segment_gaps_only",
        "improved_tracker": str(args.improved_tracker),
        "ground_truth_available": bool(ground_truth),
        "formal_identity_metrics": (
            "see outputs/mot_validation/mot_tracking_report.json; "
            "this full-run tracking_proxy is not IDF1/HOTA"
        ),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"report: {args.output}")


if __name__ == "__main__":
    main()
