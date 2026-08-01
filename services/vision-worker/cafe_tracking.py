"""CAFE 프레임 순서, 영상 시간, 추적 epoch를 관리하는 순수 파이썬 도우미."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


EXPECTED_MODEL_SHA256 = (
    "d79f8da75013b59b5b86c428fe011660b46f88d4897f1ddb044b8797a591f142"
)


@dataclass(frozen=True)
class CafeFrame:
    clip: str
    segment: int
    path: Path
    frame_number: int
    source_seconds: float
    reset_before: bool
    reset_reason: str | None = None


def numeric_frame_number(path: Path) -> int:
    digits = "".join(filter(str.isdigit, path.stem))
    if not digits:
        raise ValueError(f"프레임 번호를 읽을 수 없습니다: {path}")
    return int(digits)


def sorted_segment_paths(camera_root: Path, limit: int | None = None) -> list[Path]:
    segments = sorted(
        (path for path in camera_root.iterdir() if path.is_dir() and path.name.isdigit()),
        key=lambda path: int(path.name),
    )
    return segments[:limit] if limit is not None else segments


def load_scene_cuts(path: Path) -> dict[str, set[int]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    cameras = document.get("cameras", {})
    return {
        str(camera): {int(segment) for segment in config.get("reset_before_segments", [])}
        for camera, config in cameras.items()
    }


def segment_timing(segment_path: Path) -> tuple[float, int]:
    annotation_path = segment_path / "ann.json"
    if not annotation_path.exists():
        return 30.0, 6
    annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
    fps = float(annotation.get("fps", 30.0))
    frames_each = int(annotation.get("framesEach", 6))
    if fps <= 0 or frames_each <= 0:
        raise ValueError(f"잘못된 CAFE 시간 메타데이터: {annotation_path}")
    return fps, frames_each


def iter_camera_frames(
    cafe_root: Path,
    clip: str,
    *,
    scene_cuts: set[int] | None = None,
    segment_limit: int | None = None,
) -> Iterator[CafeFrame]:
    """CAFE 카메라의 모든 약 5fps 프레임을 영상 시간 순서로 반환한다."""
    cuts = scene_cuts or set()
    segments = sorted_segment_paths(cafe_root / clip, segment_limit)
    elapsed = 0.0
    previous_segment: int | None = None

    for segment_path in segments:
        segment = int(segment_path.name)
        frames = sorted(
            (segment_path / "images").glob("*.jpg"),
            key=numeric_frame_number,
        )
        if not frames:
            continue
        fps, frames_each = segment_timing(segment_path)
        gap = previous_segment is not None and segment != previous_segment + 1
        explicit_cut = segment in cuts
        first_segment = previous_segment is None
        reset_reason = (
            "initial"
            if first_segment
            else "segment_gap"
            if gap
            else "scene_cut"
            if explicit_cut
            else None
        )

        first_frame_number = numeric_frame_number(frames[0])
        for index, frame_path in enumerate(frames):
            frame_number = numeric_frame_number(frame_path)
            yield CafeFrame(
                clip=str(clip),
                segment=segment,
                path=frame_path,
                frame_number=frame_number,
                source_seconds=elapsed + (frame_number - first_frame_number) / fps,
                reset_before=index == 0 and reset_reason is not None,
                reset_reason=reset_reason if index == 0 else None,
            )

        last_frame_number = numeric_frame_number(frames[-1])
        elapsed += (last_frame_number - first_frame_number + frames_each) / fps
        previous_segment = segment


class OutputSampler:
    """분석 입력과 독립적으로 일정한 영상 시간 간격의 출력만 선택한다."""

    def __init__(self, interval_seconds: float = 1.0) -> None:
        if interval_seconds <= 0:
            raise ValueError("출력 간격은 0보다 커야 합니다")
        self.interval_seconds = float(interval_seconds)
        self.next_output_seconds: float | None = None

    def should_emit(self, source_seconds: float, *, force: bool = False) -> bool:
        if self.next_output_seconds is None or force:
            self.next_output_seconds = source_seconds + self.interval_seconds
            return True
        if source_seconds + 1e-6 < self.next_output_seconds:
            return False
        while self.next_output_seconds <= source_seconds + 1e-6:
            self.next_output_seconds += self.interval_seconds
        return True


class TrackingEpoch:
    def __init__(self, camera_id: str) -> None:
        self.camera_id = camera_id
        self.value = -1

    def reset(self) -> int:
        self.value += 1
        return self.value

    def public_id(self, local_track_id: int | str) -> str:
        if self.value < 0:
            raise RuntimeError("tracking epoch가 시작되지 않았습니다")
        return f"{self.camera_id}:e{self.value}:t{local_track_id}"


def reset_ultralytics_tracker(model) -> None:
    predictor = getattr(model, "predictor", None)
    trackers = getattr(predictor, "trackers", None) or []
    for tracker in trackers:
        reset = getattr(tracker, "reset", None)
        if callable(reset):
            reset()


def validate_model_file(path: Path, expected_sha256: str = EXPECTED_MODEL_SHA256) -> str:
    if not path.is_file():
        raise FileNotFoundError(
            "CAFE 파인튜닝 모델이 없습니다. "
            f"AISEYE_CAFE_MODEL에 실제 best.pt 경로를 지정하세요: {path}"
        )
    digest = hashlib.sha256()
    with path.open("rb") as model_file:
        for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if expected_sha256 and actual != expected_sha256:
        raise ValueError(
            "CAFE 모델 SHA-256이 기준 모델과 다릅니다: "
            f"expected={expected_sha256}, actual={actual}"
        )
    return actual
