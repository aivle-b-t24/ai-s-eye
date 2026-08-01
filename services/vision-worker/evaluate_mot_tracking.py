"""공식 CAFE ID 라벨로 ByteTrack 설정을 튜닝하고 MOT 지표를 검증한다.

CAFE의 ``gt_tracks.pkl``은 텍스트 평가 파일과 달리 각 행 첫 열에 세그먼트 내
사람 ID를 보존한다. 연속 세그먼트 경계에서는 마지막/첫 프레임의 위치를 매칭해
전역 ID로 연결하고, 실제 장면 전환에서만 새 ID를 발급한다. 그 결과를 MOT 형식으로
내보내 TrackEval의 HOTA, Identity, CLEAR 지표를 계산한다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment
from ultralytics import YOLO

from benchmark_tracking import read_image, recover_image_from_zip
from cafe_tracking import (
    EXPECTED_MODEL_SHA256,
    CafeFrame,
    iter_camera_frames,
    load_scene_cuts,
    reset_ultralytics_tracker,
    validate_model_file,
)
from tune_bytetrack import CANDIDATES, tracker_yaml


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_MANIFEST = SCRIPT_DIR / "mot_validation_windows.json"
DEFAULT_SCENE_CUTS = SCRIPT_DIR / "cafe_scene_cuts.json"
GT_PICKLE_MEMBER = "Cafe_Dataset/Dataset/cafe/gt_tracks.pkl"
EXPECTED_GT_SHA256 = "98ccd12267bb62fa27040f11876bab5f1d38c96f4544fe552ca6f5dcc55ff072"
TRACK_ID_EPOCH_MULTIPLIER = 100_000


@dataclass(frozen=True)
class Window:
    id: str
    camera: str
    split: str
    category: str
    start_index: int
    frame_count: int


@dataclass(frozen=True)
class LabeledFrame:
    source: CafeFrame
    epoch: int
    boxes: np.ndarray
    ids: np.ndarray


@dataclass(frozen=True)
class TrackerConfig:
    name: str
    confidence: float
    tracker: str
    reset_on_discontinuity: bool


def load_windows(path: Path) -> list[Window]:
    document = json.loads(path.read_text(encoding="utf-8"))
    windows = [Window(**item) for item in document["windows"]]
    ids = [window.id for window in windows]
    if len(ids) != len(set(ids)):
        raise ValueError("MOT window id가 중복되었습니다")
    for camera in ("5", "21"):
        selected = [window for window in windows if window.camera == camera]
        if len(selected) != 8:
            raise ValueError(f"camera {camera} window는 정확히 8개여야 합니다")
        if sum(window.split == "tune" for window in selected) != 4:
            raise ValueError(f"camera {camera} tune window는 정확히 4개여야 합니다")
        if sum(window.split == "test" for window in selected) != 4:
            raise ValueError(f"camera {camera} test window는 정확히 4개여야 합니다")
    return windows


def load_identity_ground_truth(zip_path: Path) -> dict:
    """신뢰된 로컬 CAFE 배포 ZIP에서 공식 identity pickle을 읽는다."""
    if not zip_path.is_file():
        raise FileNotFoundError(f"CAFE 원본 ZIP이 없습니다: {zip_path}")
    with zipfile.ZipFile(zip_path) as archive:
        if GT_PICKLE_MEMBER not in archive.namelist():
            raise FileNotFoundError(f"ZIP에 {GT_PICKLE_MEMBER}가 없습니다")
        payload = archive.read(GT_PICKLE_MEMBER)
    digest = hashlib.sha256(payload).hexdigest()
    if digest != EXPECTED_GT_SHA256:
        raise ValueError(
            "CAFE identity GT 해시가 기준 데이터와 다릅니다: "
            f"expected={EXPECTED_GT_SHA256}, actual={digest}"
        )
    return pickle.loads(payload)  # noqa: S301 - hash-verified official dataset


def normalized_gt_rows(ground_truth: dict, camera: str, frame: CafeFrame) -> np.ndarray:
    rows = ground_truth.get((int(camera), frame.segment), {}).get(frame.frame_number)
    if rows is None:
        return np.empty((0, 5), dtype=np.float64)
    result = np.asarray(rows, dtype=np.float64)
    if result.size == 0:
        return np.empty((0, 5), dtype=np.float64)
    if result.ndim != 2 or result.shape[1] != 5:
        raise ValueError(
            f"잘못된 GT shape: camera={camera}, segment={frame.segment}, "
            f"frame={frame.frame_number}, shape={result.shape}"
        )
    # 공식 pickle에는 드물게 좌표가 모두 같은 placeholder 행이 있다. 실제 사람
    # bbox가 아니므로 MOT 정답과 경계 ID 연결 양쪽에서 제외한다.
    valid = (
        np.isfinite(result).all(axis=1)
        & (result[:, 3] > result[:, 1])
        & (result[:, 4] > result[:, 2])
    )
    return result[valid]


def stitch_segment_identities(
    previous_boxes: np.ndarray,
    previous_ids: np.ndarray,
    current_rows: np.ndarray,
    allocate_id,
) -> tuple[dict[int, int], dict]:
    """연속 세그먼트 경계의 local ID를 이전 전역 ID에 연결한다."""
    current_local_ids = current_rows[:, 0].astype(np.int64)
    current_boxes = current_rows[:, 1:5]
    mapping: dict[int, int] = {}
    matches = []
    rejected = []

    if len(previous_boxes) and len(current_boxes):
        ious = box_iou_matrix(previous_boxes, current_boxes)
        previous_feet = np.column_stack(
            ((previous_boxes[:, 0] + previous_boxes[:, 2]) / 2, previous_boxes[:, 3])
        )
        current_feet = np.column_stack(
            ((current_boxes[:, 0] + current_boxes[:, 2]) / 2, current_boxes[:, 3])
        )
        foot_distances = np.linalg.norm(
            previous_feet[:, None, :] - current_feet[None, :, :], axis=2
        )
        previous_heights = np.maximum(previous_boxes[:, 3] - previous_boxes[:, 1], 1e-6)
        current_heights = np.maximum(current_boxes[:, 3] - current_boxes[:, 1], 1e-6)
        size_deltas = np.abs(
            np.log(previous_heights[:, None] / current_heights[None, :])
        )
        cost = (1 - ious) + foot_distances * 3 + size_deltas * 0.2
        previous_indexes, current_indexes = linear_sum_assignment(cost)
        for previous_index, current_index in zip(previous_indexes, current_indexes):
            iou = float(ious[previous_index, current_index])
            foot_distance = float(foot_distances[previous_index, current_index])
            size_delta = float(size_deltas[previous_index, current_index])
            detail = {
                "previous_global_id": int(previous_ids[previous_index]),
                "current_local_id": int(current_local_ids[current_index]),
                "iou": round(iou, 6),
                "foot_distance": round(foot_distance, 6),
                "log_height_delta": round(size_delta, 6),
            }
            # 경계 프레임은 0.2초 차이다. IoU가 조금 낮더라도 발 위치와 사람
            # 크기가 함께 가까울 때만 같은 사람으로 인정한다.
            accepted = iou >= 0.10 or (foot_distance <= 0.12 and size_delta <= 0.50)
            if accepted:
                mapping[int(current_local_ids[current_index])] = int(
                    previous_ids[previous_index]
                )
                matches.append(detail)
            else:
                rejected.append(detail)

    for local_id in current_local_ids:
        local_id = int(local_id)
        if local_id not in mapping:
            mapping[local_id] = int(allocate_id())
    audit = {
        "matches": matches,
        "rejected": rejected,
        "previous_count": int(len(previous_ids)),
        "current_count": int(len(current_local_ids)),
        "matched_count": len(matches),
        "new_identity_count": int(len(current_local_ids) - len(matches)),
    }
    return mapping, audit


def build_labeled_frames(
    cafe_root: Path,
    camera: str,
    ground_truth: dict,
    cuts: set[int],
    stitch_audit: list[dict] | None = None,
) -> list[LabeledFrame]:
    labeled: list[LabeledFrame] = []
    epoch = -1
    current_segment: int | None = None
    local_to_global: dict[int, int] = {}
    next_global_id = 1

    def allocate_id() -> int:
        nonlocal next_global_id
        identity = next_global_id
        next_global_id += 1
        return identity

    for source in iter_camera_frames(cafe_root, camera, scene_cuts=cuts):
        rows = normalized_gt_rows(ground_truth, camera, source)
        new_segment = source.segment != current_segment
        if new_segment:
            previous_segment = current_segment
            if source.reset_before:
                epoch += 1
                local_to_global = {}
            elif labeled:
                local_to_global, audit = stitch_segment_identities(
                    labeled[-1].boxes,
                    labeled[-1].ids,
                    rows,
                    allocate_id,
                )
                if stitch_audit is not None:
                    stitch_audit.append(
                        {
                            "camera": str(camera),
                            "previous_segment": previous_segment,
                            "current_segment": source.segment,
                            **audit,
                        }
                    )
            current_segment = source.segment

        ids = []
        for local_id in rows[:, 0].astype(np.int64):
            local_id = int(local_id)
            if local_id not in local_to_global:
                local_to_global[local_id] = allocate_id()
            ids.append(local_to_global[local_id])
        labeled_frame = LabeledFrame(
            source=source,
            epoch=epoch,
            boxes=rows[:, 1:5].copy(),
            ids=np.asarray(ids, dtype=np.int64),
        )
        labeled.append(labeled_frame)
    return labeled


def materialize_windows(
    windows: list[Window],
    frames_by_camera: dict[str, list[LabeledFrame]],
) -> dict[str, list[LabeledFrame]]:
    result = {}
    for window in windows:
        camera_frames = frames_by_camera[window.camera]
        end = window.start_index + window.frame_count
        if window.start_index < 0 or end > len(camera_frames):
            raise ValueError(f"window 범위가 데이터 밖입니다: {window.id}")
        selected = camera_frames[window.start_index:end]
        if len(selected) != window.frame_count:
            raise ValueError(f"window frame 수가 맞지 않습니다: {window.id}")
        cut_count = sum(
            frame.source.reset_before
            and frame.source.reset_reason in {"scene_cut", "segment_gap"}
            for frame in selected
        )
        if window.category == "scene_cut" and cut_count != 1:
            raise ValueError(f"scene_cut window에는 전환이 정확히 하나여야 합니다: {window.id}")
        if window.category != "scene_cut" and cut_count:
            raise ValueError(f"일반 window에 장면 전환이 포함됐습니다: {window.id}")
        result[window.id] = selected
    return result


def pixel_boxes(boxes: np.ndarray, width: int, height: int) -> np.ndarray:
    if len(boxes) == 0:
        return np.empty((0, 4), dtype=np.float64)
    scaled = boxes.copy()
    scaled[:, [0, 2]] *= width
    scaled[:, [1, 3]] *= height
    return scaled


def box_iou_matrix(gt_boxes: np.ndarray, tracker_boxes: np.ndarray) -> np.ndarray:
    if len(gt_boxes) == 0 or len(tracker_boxes) == 0:
        return np.zeros((len(gt_boxes), len(tracker_boxes)), dtype=np.float64)
    top_left = np.maximum(gt_boxes[:, None, :2], tracker_boxes[None, :, :2])
    bottom_right = np.minimum(gt_boxes[:, None, 2:], tracker_boxes[None, :, 2:])
    intersection_wh = np.maximum(bottom_right - top_left, 0)
    intersection = intersection_wh[:, :, 0] * intersection_wh[:, :, 1]
    gt_area = np.prod(np.maximum(gt_boxes[:, 2:] - gt_boxes[:, :2], 0), axis=1)
    tracker_area = np.prod(
        np.maximum(tracker_boxes[:, 2:] - tracker_boxes[:, :2], 0), axis=1
    )
    union = gt_area[:, None] + tracker_area[None, :] - intersection
    return np.divide(intersection, union, out=np.zeros_like(intersection), where=union > 0)


def compact_ids(id_frames: list[np.ndarray]) -> tuple[list[np.ndarray], int]:
    unique = sorted({int(identity) for identities in id_frames for identity in identities})
    mapping = {identity: index for index, identity in enumerate(unique)}
    return [
        np.asarray([mapping[int(identity)] for identity in identities], dtype=np.int64)
        for identities in id_frames
    ], len(unique)


def trackeval_data(
    labeled_frames: list[LabeledFrame],
    predictions: list[dict],
) -> dict:
    gt_ids_raw = [frame.ids for frame in labeled_frames]
    tracker_ids_raw = [
        np.asarray(frame["ids"], dtype=np.int64) for frame in predictions
    ]
    gt_ids, num_gt_ids = compact_ids(gt_ids_raw)
    tracker_ids, num_tracker_ids = compact_ids(tracker_ids_raw)
    gt_dets = []
    tracker_dets = []
    similarity_scores = []
    for labeled, predicted in zip(labeled_frames, predictions):
        width = int(predicted["width"])
        height = int(predicted["height"])
        gt_boxes = pixel_boxes(labeled.boxes, width, height)
        predicted_boxes = np.asarray(predicted["boxes"], dtype=np.float64).reshape(-1, 4)
        gt_dets.append(gt_boxes)
        tracker_dets.append(predicted_boxes)
        similarity_scores.append(box_iou_matrix(gt_boxes, predicted_boxes))
    return {
        "num_timesteps": len(labeled_frames),
        "gt_ids": gt_ids,
        "tracker_ids": tracker_ids,
        "gt_dets": gt_dets,
        "tracker_dets": tracker_dets,
        "similarity_scores": similarity_scores,
        "num_gt_dets": sum(len(ids) for ids in gt_ids),
        "num_tracker_dets": sum(len(ids) for ids in tracker_ids),
        "num_gt_ids": num_gt_ids,
        "num_tracker_ids": num_tracker_ids,
    }


def import_trackeval():
    try:
        import trackeval
    except ImportError as exc:
        raise RuntimeError(
            "TrackEval이 없습니다. services/vision-worker/requirements.txt를 설치하세요."
        ) from exc
    return trackeval


def evaluate_sequences(
    window_map: dict[str, list[LabeledFrame]],
    prediction_map: dict[str, list[dict]],
) -> dict:
    trackeval = import_trackeval()
    metrics = {
        "hota": trackeval.metrics.HOTA(),
        "identity": trackeval.metrics.Identity({"PRINT_CONFIG": False}),
        "clear": trackeval.metrics.CLEAR({"PRINT_CONFIG": False}),
    }
    per_sequence_raw = {}
    for sequence, labeled_frames in window_map.items():
        data = trackeval_data(labeled_frames, prediction_map[sequence])
        per_sequence_raw[sequence] = {
            name: metric.eval_sequence(data) for name, metric in metrics.items()
        }

    def combine(selected: list[str]) -> dict:
        combined = {
            name: metric.combine_sequences(
                {sequence: per_sequence_raw[sequence][name] for sequence in selected}
            )
            for name, metric in metrics.items()
        }
        total_frames = sum(len(window_map[sequence]) for sequence in selected)
        count_absolute_error = sum(
            abs(len(gt.ids) - len(pred["ids"]))
            for sequence in selected
            for gt, pred in zip(window_map[sequence], prediction_map[sequence])
        )
        hota = combined["hota"]
        identity = combined["identity"]
        clear = combined["clear"]
        return {
            "sequences": selected,
            "frames": total_frames,
            "HOTA": round(float(np.mean(hota["HOTA"])) * 100, 3),
            "DetA": round(float(np.mean(hota["DetA"])) * 100, 3),
            "AssA": round(float(np.mean(hota["AssA"])) * 100, 3),
            "IDF1": round(float(identity["IDF1"]) * 100, 3),
            "IDP": round(float(identity["IDP"]) * 100, 3),
            "IDR": round(float(identity["IDR"]) * 100, 3),
            "IDSW": int(clear["IDSW"]),
            "Frag": int(clear["Frag"]),
            "FP": int(clear["CLR_FP"]),
            "FN": int(clear["CLR_FN"]),
            "precision_iou50": round(float(clear["CLR_Pr"]) * 100, 3),
            "recall_iou50": round(float(clear["CLR_Re"]) * 100, 3),
            "count_mae": round(count_absolute_error / max(total_frames, 1), 4),
        }

    all_sequences = list(window_map)
    result = {
        "all": combine(all_sequences),
        "by_camera": {},
        "by_category": {},
        "per_sequence": {
            sequence: combine([sequence]) for sequence in all_sequences
        },
    }
    for camera in ("5", "21"):
        selected = [sequence for sequence in all_sequences if sequence.startswith(f"cam{camera}-")]
        if selected:
            result["by_camera"][camera] = combine(selected)
    for category, token in (
        ("normal", "-normal-"),
        ("crowded_occluded", "-crowd-"),
        ("scene_cut", "-cut-"),
    ):
        selected = [sequence for sequence in all_sequences if token in sequence]
        if selected:
            result["by_category"][category] = combine(selected)
    return result


def discontinuity_id_reuse(
    window_map: dict[str, list[LabeledFrame]],
    prediction_map: dict[str, list[dict]],
    reasons: set[str] | None = None,
) -> dict:
    reused = possible = cut_frames = 0
    for sequence, labeled_frames in window_map.items():
        predictions = prediction_map[sequence]
        for index, labeled in enumerate(labeled_frames):
            if (
                index == 0
                or not labeled.source.reset_before
                or labeled.source.reset_reason == "initial"
                or (
                    reasons is not None
                    and labeled.source.reset_reason not in reasons
                )
            ):
                continue
            previous_ids = {int(identity) for identity in predictions[index - 1]["ids"]}
            current_ids = {int(identity) for identity in predictions[index]["ids"]}
            reused += len(previous_ids & current_ids)
            possible += min(len(previous_ids), len(current_ids))
            cut_frames += 1
    return {
        "boundary_frames": cut_frames,
        "reused_ids": reused,
        "possible_ids": possible,
        "reuse_rate_percent": round(reused / max(possible, 1) * 100, 3),
    }


def write_mot_dataset(
    output_root: Path,
    window_map: dict[str, list[LabeledFrame]],
    source_zip: Path,
) -> None:
    for sequence, frames in window_map.items():
        sequence_root = output_root / sequence
        image_root = sequence_root / "img1"
        gt_root = sequence_root / "gt"
        image_root.mkdir(parents=True, exist_ok=True)
        gt_root.mkdir(parents=True, exist_ok=True)
        first_image = read_image(frames[0].source.path)
        if first_image is None:
            first_image = recover_image_from_zip(
                source_zip, frames[0].source.path.parents[3], frames[0].source.path
            )
        if first_image is None:
            raise ValueError(f"첫 이미지를 읽을 수 없습니다: {sequence}")
        height, width = first_image.shape[:2]
        gt_lines = []
        frame_map = []
        for index, frame in enumerate(frames, 1):
            target = image_root / f"{index:06d}.jpg"
            if not target.exists():
                target.symlink_to(frame.source.path)
            boxes = pixel_boxes(frame.boxes, width, height)
            for identity, box in zip(frame.ids, boxes):
                x1, y1, x2, y2 = box
                gt_lines.append(
                    f"{index},{int(identity)},{x1:.3f},{y1:.3f},"
                    f"{x2 - x1:.3f},{y2 - y1:.3f},1,1,1"
                )
            frame_map.append(
                {
                    "mot_frame": index,
                    "segment": frame.source.segment,
                    "source_frame": frame.source.frame_number,
                    "source_seconds": round(frame.source.source_seconds, 6),
                    "tracking_epoch": frame.epoch,
                    "reset_before": frame.source.reset_before,
                    "reset_reason": frame.source.reset_reason,
                }
            )
        (gt_root / "gt.txt").write_text("\n".join(gt_lines) + "\n", encoding="utf-8")
        (sequence_root / "seqinfo.ini").write_text(
            "[Sequence]\n"
            f"name={sequence}\n"
            "imDir=img1\n"
            "frameRate=5\n"
            f"seqLength={len(frames)}\n"
            f"imWidth={width}\n"
            f"imHeight={height}\n"
            "imExt=.jpg\n",
            encoding="utf-8",
        )
        (sequence_root / "frame_map.json").write_text(
            json.dumps(frame_map, indent=2), encoding="utf-8"
        )


def selected_identity_boundaries(
    window_map: dict[str, list[LabeledFrame]],
    stitch_audit: list[dict],
) -> list[dict]:
    """평가 window 안의 연속 세그먼트 경계만 고정 검수 목록으로 만든다."""
    audit_by_boundary = {
        (item["camera"], item["previous_segment"], item["current_segment"]): item
        for item in stitch_audit
    }
    selected: dict[tuple[str, int, int], dict] = {}
    for window_id, frames in window_map.items():
        for previous, current in zip(frames, frames[1:]):
            if previous.source.segment == current.source.segment or current.source.reset_before:
                continue
            key = (
                str(current.source.clip),
                previous.source.segment,
                current.source.segment,
            )
            item = selected.setdefault(
                key,
                {
                    "camera": key[0],
                    "previous_segment": key[1],
                    "current_segment": key[2],
                    "windows": [],
                    "previous_frame": previous,
                    "current_frame": current,
                    "audit": audit_by_boundary[key],
                },
            )
            item["windows"].append(window_id)
    return list(selected.values())


def _identity_color(identity: int) -> tuple[int, int, int]:
    return (
        60 + (identity * 67) % 180,
        60 + (identity * 113) % 180,
        60 + (identity * 151) % 180,
    )


def _draw_identity_panel(frame: LabeledFrame, source_zip: Path) -> np.ndarray:
    image = read_image(frame.source.path)
    if image is None:
        image = recover_image_from_zip(
            source_zip, frame.source.path.parents[3], frame.source.path
        )
    if image is None:
        raise ValueError(f"검수 이미지를 읽을 수 없습니다: {frame.source.path}")
    panel = cv2.resize(image, (480, 270))
    for identity, box in zip(frame.ids, pixel_boxes(frame.boxes, 480, 270)):
        x1, y1, x2, y2 = map(int, box)
        color = _identity_color(int(identity))
        cv2.rectangle(panel, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            panel,
            f"G{int(identity)}",
            (x1, max(y1 - 4, 13)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            color,
            1,
            cv2.LINE_AA,
        )
    return panel


def write_identity_stitch_audit(
    output_root: Path,
    boundaries: list[dict],
    source_zip: Path,
) -> None:
    """ID 연결 JSON과 사람이 좌우로 대조할 contact sheet를 저장한다."""
    output_root.mkdir(parents=True, exist_ok=True)
    serializable = [
        {
            "camera": item["camera"],
            "previous_segment": item["previous_segment"],
            "current_segment": item["current_segment"],
            "windows": item["windows"],
            **item["audit"],
        }
        for item in boundaries
    ]
    (output_root / "identity_stitch_audit.json").write_text(
        json.dumps(serializable, indent=2), encoding="utf-8"
    )
    for camera in ("5", "21"):
        camera_items = [item for item in boundaries if item["camera"] == camera]
        for page_index, start in enumerate(range(0, len(camera_items), 8), 1):
            page_items = camera_items[start : start + 8]
            sheet = np.zeros((1080, 1920, 3), dtype=np.uint8)
            for offset, item in enumerate(page_items):
                row, column = divmod(offset, 2)
                previous = _draw_identity_panel(item["previous_frame"], source_zip)
                current = _draw_identity_panel(item["current_frame"], source_zip)
                cell = np.hstack((previous, current))
                label = (
                    f"cam{camera} {item['previous_segment']} -> "
                    f"{item['current_segment']}  matched={item['audit']['matched_count']} "
                    f"new={item['audit']['new_identity_count']}"
                )
                cv2.rectangle(cell, (0, 0), (960, 24), (0, 0, 0), -1)
                cv2.putText(
                    cell,
                    label,
                    (8, 17),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.48,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )
                y, x = row * 270, column * 960
                sheet[y : y + 270, x : x + 960] = cell
            cv2.imwrite(
                str(output_root / f"identity_stitch_cam{camera}_{page_index}.jpg"),
                sheet,
            )


def prediction_id(local_id: int, epoch: int, reset_on_discontinuity: bool) -> int:
    return (
        local_id + epoch * TRACK_ID_EPOCH_MULTIPLIER
        if reset_on_discontinuity
        else local_id
    )


def run_tracker(
    config: TrackerConfig,
    model_path: Path,
    window_map: dict[str, list[LabeledFrame]],
    source_zip: Path,
) -> tuple[dict[str, list[dict]], dict]:
    model = YOLO(model_path)
    prediction_map = {}
    decoded = recovered = 0
    started = time.perf_counter()
    for sequence, frames in window_map.items():
        reset_ultralytics_tracker(model)
        prediction_epoch = 0
        predictions = []
        for index, labeled in enumerate(frames):
            discontinuity = (
                index > 0
                and labeled.source.reset_before
                and labeled.source.reset_reason != "initial"
            )
            if config.reset_on_discontinuity and discontinuity:
                reset_ultralytics_tracker(model)
                prediction_epoch += 1
            image = read_image(labeled.source.path)
            if image is None:
                image = recover_image_from_zip(
                    source_zip,
                    labeled.source.path.parents[3],
                    labeled.source.path,
                )
                recovered += image is not None
            if image is None:
                raise ValueError(f"이미지를 읽을 수 없습니다: {labeled.source.path}")
            result = model.track(
                image,
                persist=True,
                tracker=config.tracker,
                classes=[0],
                conf=config.confidence,
                iou=0.5,
                agnostic_nms=True,
                verbose=False,
            )[0]
            height, width = image.shape[:2]
            if result.boxes is None or result.boxes.id is None:
                boxes = np.empty((0, 4), dtype=np.float64)
                ids = []
                confidence = []
            else:
                boxes = result.boxes.xyxy.cpu().numpy()
                local_ids = result.boxes.id.cpu().numpy().astype(int).tolist()
                ids = [
                    prediction_id(
                        local_id,
                        prediction_epoch,
                        config.reset_on_discontinuity,
                    )
                    for local_id in local_ids
                ]
                confidence = result.boxes.conf.cpu().numpy().astype(float).tolist()
            predictions.append(
                {
                    "frame": index + 1,
                    "width": width,
                    "height": height,
                    "ids": ids,
                    "boxes": boxes.astype(float).tolist(),
                    "confidence": confidence,
                    "reset_before": bool(discontinuity),
                }
            )
            decoded += 1
        prediction_map[sequence] = predictions
        print(f"  {config.name}: {sequence} ({len(frames)} frames)", flush=True)
    elapsed = time.perf_counter() - started
    return prediction_map, {
        "frames": decoded,
        "recovered_from_zip": recovered,
        "elapsed_seconds": round(elapsed, 3),
        "throughput_fps": round(decoded / max(elapsed, 1e-9), 3),
    }


def save_predictions(path: Path, prediction_map: dict[str, list[dict]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prediction_map), encoding="utf-8")


def load_predictions(path: Path) -> dict[str, list[dict]]:
    return json.loads(path.read_text(encoding="utf-8"))


def candidate_configs(temp_dir: Path) -> list[TrackerConfig]:
    configs = []
    for high, buffer, match in CANDIDATES:
        name = f"h{int(high * 100)}-b{buffer}-m{int(match * 100)}"
        tracker_path = temp_dir / f"{name}.yaml"
        tracker_path.write_text(tracker_yaml(high, buffer, match), encoding="utf-8")
        configs.append(
            TrackerConfig(
                name=name,
                confidence=0.10,
                tracker=str(tracker_path),
                reset_on_discontinuity=True,
            )
        )
    return configs


def tracker_result(
    config: TrackerConfig,
    model_path: Path,
    window_map: dict[str, list[LabeledFrame]],
    source_zip: Path,
    prediction_root: Path,
    reuse: bool,
) -> dict:
    prediction_path = prediction_root / f"{config.name}.json"
    runtime_path = prediction_root / f"{config.name}.runtime.json"
    if reuse and prediction_path.is_file():
        predictions = load_predictions(prediction_path)
        if runtime_path.is_file():
            runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
            runtime["reused_predictions"] = True
        else:
            runtime = {"reused": True, "frames": sum(map(len, predictions.values()))}
    else:
        predictions, runtime = run_tracker(config, model_path, window_map, source_zip)
        save_predictions(prediction_path, predictions)
        runtime_path.write_text(json.dumps(runtime, indent=2), encoding="utf-8")
    metrics = evaluate_sequences(window_map, predictions)
    return {
        "config": config.__dict__,
        "runtime": runtime,
        "metrics": metrics,
        "boundary_id_reuse": discontinuity_id_reuse(window_map, predictions),
        "scene_cut_id_reuse": discontinuity_id_reuse(
            window_map,
            predictions,
            reasons={"scene_cut", "segment_gap"},
        ),
    }


def render_comparison_video(
    output_path: Path,
    labeled_frames: list[LabeledFrame],
    baseline: list[dict],
    candidate: list[dict],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        5.0,
        (1920, 540),
    )
    if not writer.isOpened():
        raise RuntimeError(f"비디오 writer를 열 수 없습니다: {output_path}")
    try:
        for labeled, base_frame, candidate_frame in zip(labeled_frames, baseline, candidate):
            image = read_image(labeled.source.path)
            if image is None:
                continue
            image = cv2.resize(image, (960, 540))
            panels = []
            for title, predicted, color in (
                ("BASELINE", base_frame, (50, 50, 255)),
                ("CANDIDATE", candidate_frame, (255, 120, 30)),
            ):
                panel = image.copy()
                gt_boxes = pixel_boxes(labeled.boxes, 960, 540)
                for identity, box in zip(labeled.ids, gt_boxes):
                    x1, y1, x2, y2 = map(int, box)
                    cv2.rectangle(panel, (x1, y1), (x2, y2), (50, 220, 50), 1)
                    cv2.putText(
                        panel,
                        f"G{int(identity) % TRACK_ID_EPOCH_MULTIPLIER}",
                        (x1, max(y1 - 3, 12)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.35,
                        (50, 220, 50),
                        1,
                        cv2.LINE_AA,
                    )
                scale_x = 960 / predicted["width"]
                scale_y = 540 / predicted["height"]
                for identity, raw_box in zip(predicted["ids"], predicted["boxes"]):
                    x1, y1, x2, y2 = map(
                        int,
                        (
                            raw_box[0] * scale_x,
                            raw_box[1] * scale_y,
                            raw_box[2] * scale_x,
                            raw_box[3] * scale_y,
                        ),
                    )
                    cv2.rectangle(panel, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(
                        panel,
                        f"T{int(identity) % TRACK_ID_EPOCH_MULTIPLIER}",
                        (x1, min(y2 + 13, 538)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.4,
                        color,
                        1,
                        cv2.LINE_AA,
                    )
                cv2.putText(
                    panel,
                    title,
                    (15, 28),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    color,
                    2,
                    cv2.LINE_AA,
                )
                panels.append(panel)
            writer.write(np.hstack(panels))
    finally:
        writer.release()


def main() -> None:
    parser = argparse.ArgumentParser(description="CAFE 공식 ID 라벨 기반 MOT 평가")
    parser.add_argument("--cafe-root", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--gt-zip", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--output",
        type=Path,
        default=SCRIPT_DIR / "outputs" / "mot_validation",
    )
    parser.add_argument("--reuse", action="store_true")
    parser.add_argument("--skip-videos", action="store_true")
    args = parser.parse_args()

    model_sha = validate_model_file(args.model, EXPECTED_MODEL_SHA256)
    windows = load_windows(args.manifest)
    cuts = load_scene_cuts(DEFAULT_SCENE_CUTS)
    ground_truth = load_identity_ground_truth(args.gt_zip)
    stitch_audit: list[dict] = []
    frames_by_camera = {
        camera: build_labeled_frames(
            args.cafe_root,
            camera,
            ground_truth,
            cuts.get(camera, set()),
            stitch_audit,
        )
        for camera in ("5", "21")
    }
    materialized = materialize_windows(windows, frames_by_camera)
    write_mot_dataset(args.output / "dataset", materialized, args.gt_zip)
    identity_boundaries = selected_identity_boundaries(materialized, stitch_audit)
    write_identity_stitch_audit(args.output / "audit", identity_boundaries, args.gt_zip)
    tune_ids = {window.id for window in windows if window.split == "tune"}
    test_ids = {window.id for window in windows if window.split == "test"}
    tune_windows = {key: value for key, value in materialized.items() if key in tune_ids}
    test_windows = {key: value for key, value in materialized.items() if key in test_ids}

    prediction_root = args.output / "predictions"
    with tempfile.TemporaryDirectory(prefix="aiseye-mot-trackers-") as temp:
        candidates = []
        for config in candidate_configs(Path(temp)):
            result = tracker_result(
                config,
                args.model,
                tune_windows,
                args.gt_zip,
                prediction_root / "tune",
                args.reuse,
            )
            candidates.append(result)
        candidates.sort(
            key=lambda result: (
                -result["metrics"]["all"]["IDF1"],
                -result["metrics"]["all"]["HOTA"],
                result["metrics"]["all"]["FP"],
            )
        )
        selected = candidates[0]
        selected_config = TrackerConfig(**selected["config"])

        baseline_config = TrackerConfig(
            name="baseline",
            confidence=0.30,
            tracker="bytetrack.yaml",
            reset_on_discontinuity=False,
        )
        baseline = tracker_result(
            baseline_config,
            args.model,
            test_windows,
            args.gt_zip,
            prediction_root / "test",
            args.reuse,
        )
        current_default_config = TrackerConfig(
            name="baseline-reset",
            confidence=0.30,
            tracker="bytetrack.yaml",
            reset_on_discontinuity=True,
        )
        current_default = tracker_result(
            current_default_config,
            args.model,
            test_windows,
            args.gt_zip,
            prediction_root / "test",
            args.reuse,
        )
        candidate = tracker_result(
            selected_config,
            args.model,
            test_windows,
            args.gt_zip,
            prediction_root / "test",
            args.reuse,
        )

    baseline_predictions = load_predictions(prediction_root / "test" / "baseline.json")
    candidate_predictions = load_predictions(
        prediction_root / "test" / f"{selected_config.name}.json"
    )
    if not args.skip_videos:
        for sequence, labeled_frames in test_windows.items():
            render_comparison_video(
                args.output / "videos" / f"{sequence}.mp4",
                labeled_frames,
                baseline_predictions[sequence],
                candidate_predictions[sequence],
            )

    baseline_all = baseline["metrics"]["all"]
    current_default_all = current_default["metrics"]["all"]
    candidate_all = candidate["metrics"]["all"]
    idf1_gain = candidate_all["IDF1"] - baseline_all["IDF1"]
    idsw_reduction = (
        (baseline_all["IDSW"] - candidate_all["IDSW"])
        / max(baseline_all["IDSW"], 1)
        * 100
    )
    camera_not_worse = all(
        candidate["metrics"]["by_camera"][camera]["IDF1"]
        >= baseline["metrics"]["by_camera"][camera]["IDF1"]
        for camera in ("5", "21")
    )
    precision_delta = (
        candidate_all["precision_iou50"] - baseline_all["precision_iou50"]
    )
    candidate_cut_reuse = candidate["scene_cut_id_reuse"]["reused_ids"]
    verdict = {
        "idf1_gain_pp": round(idf1_gain, 3),
        "idf1_gain_at_least_3pp": idf1_gain >= 3.0,
        "idsw_reduction_percent": round(idsw_reduction, 3),
        "idsw_reduction_at_least_30_percent": idsw_reduction >= 30.0,
        "both_cameras_not_worse": camera_not_worse,
        "scene_cut_previous_id_reuse": candidate_cut_reuse,
        "scene_cut_previous_id_reuse_is_zero": candidate_cut_reuse == 0,
        "precision_delta_pp": round(precision_delta, 3),
        "precision_drop_within_1pp": precision_delta >= -1.0,
        "count_mae_not_worse": candidate_all["count_mae"] <= baseline_all["count_mae"],
        "current_default_idf1_gain_pp": round(
            current_default_all["IDF1"] - baseline_all["IDF1"], 3
        ),
        "candidate_idf1_vs_current_default_pp": round(
            candidate_all["IDF1"] - current_default_all["IDF1"], 3
        ),
        "candidate_idswitch_vs_current_default": (
            candidate_all["IDSW"] - current_default_all["IDSW"]
        ),
        "recommended_runtime_profile": "baseline",
        "formal_tracking_gate_passed": (
            idf1_gain >= 3.0
            and idsw_reduction >= 30.0
            and camera_not_worse
            and candidate_cut_reuse == 0
            and precision_delta >= -1.0
            and candidate_all["count_mae"] <= baseline_all["count_mae"]
        ),
    }
    report = {
        "schema_version": "1.1",
        "model_sha256": model_sha,
        "identity_ground_truth": {
            "archive": str(args.gt_zip),
            "member": GT_PICKLE_MEMBER,
            "sha256": EXPECTED_GT_SHA256,
            "format": (
                "normalized [local_id, x1, y1, x2, y2]; local identities stitched "
                "across continuous segments and reset at verified cuts/gaps"
            ),
            "selected_boundary_audit": str(
                args.output / "audit" / "identity_stitch_audit.json"
            ),
            "selected_boundary_count": len(identity_boundaries),
        },
        "window_manifest": str(args.manifest),
        "tuning": {
            "selection_rule": "highest IDF1; tie: HOTA then FP",
            "selected": selected_config.name,
            "ranking": candidates,
        },
        "held_out_test": {
            "legacy_baseline": baseline,
            "current_default": current_default,
            "candidate": candidate,
        },
        "verdict": verdict,
    }
    report_path = args.output / "mot_tracking_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "selected": selected_config.name,
                "legacy_baseline": baseline_all,
                "current_default": current_default_all,
                "candidate": candidate_all,
                "verdict": verdict,
                "report": str(report_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
