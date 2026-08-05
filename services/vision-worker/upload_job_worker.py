#!/usr/bin/env python3
"""업로드형 온보딩 분석 job을 가져와 state/snapshot을 API에 올리는 GPU 워커.

미니PC API(Tailscale) + INTERNAL_API_KEY 로 동작한다.

  export AISEYE_API=http://100.x.x.x:8000
  export INTERNAL_API_KEY=...
  export AISEYE_CAFE_MODEL=/path/to/best.pt   # 있으면 YOLO 추적 활성화
  python upload_job_worker.py --loop

AISEYE_CAFE_MODEL 이 없으면 프레임 추출 + 빈 ingest state만 올린다.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tempfile
import threading
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from typing import Callable

import urllib.error
import urllib.request

DEFAULT_CAFE_MODEL = "/home/kokdo/datasets/ai-s-eye/models/best.pt"
WORKER_DIR = Path(__file__).resolve().parent
REPLAY_CACHE_DIR = Path(
    os.getenv(
        "AISEYE_UPLOAD_REPLAY_DIR",
        str(WORKER_DIR / "outputs" / "upload-replay"),
    )
)


def _headers(api_key: str | None) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["X-Internal-Api-Key"] = api_key
    return headers


def http_json(method: str, url: str, api_key: str | None, data: bytes | None = None):
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            **_headers(api_key),
            **({"Content-Type": "application/json"} if data is not None else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        body = response.read()
        if not body:
            return None
        return json.loads(body.decode("utf-8"))


def http_bytes(url: str, api_key: str | None) -> bytes:
    request = urllib.request.Request(url, headers=_headers(api_key), method="GET")
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.read()


def claim_job(api: str, api_key: str | None, worker_id: str) -> dict | None:
    try:
        return http_json(
            "GET",
            f"{api.rstrip('/')}/internal/analysis-jobs/next?worker_id={worker_id}",
            api_key,
        )
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def patch_job(
    api: str,
    api_key: str | None,
    job_id: str,
    status: str,
    error: str | None = None,
    *,
    progress_percent: float | None = None,
    processed_frames: int | None = None,
    total_frames: int | None = None,
    stage_message: str | None = None,
):
    payload: dict = {"status": status, "worker_id": os.getenv("HOSTNAME", "gpu-worker")}
    if error is not None:
        payload["error_message"] = error
    if progress_percent is not None:
        payload["progress_percent"] = round(progress_percent, 1)
    if processed_frames is not None:
        payload["processed_frames"] = processed_frames
    if total_frames is not None:
        payload["total_frames"] = total_frames
    if stage_message is not None:
        payload["stage_message"] = stage_message
    http_json(
        "PATCH",
        f"{api.rstrip('/')}/internal/analysis-jobs/{job_id}",
        api_key,
        json.dumps(payload).encode("utf-8"),
    )


def post_json(api: str, api_key: str | None, path: str, payload: dict) -> None:
    http_json(
        "POST",
        f"{api.rstrip('/')}{path}",
        api_key,
        json.dumps(payload).encode("utf-8"),
    )


def post_snapshot(api: str, api_key: str | None, store_id: str, image_bytes: bytes) -> None:
    boundary = "----aiseeyeBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="frame.jpg"\r\n'
        f"Content-Type: image/jpeg\r\n\r\n"
    ).encode("utf-8") + image_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
    request = urllib.request.Request(
        f"{api.rstrip('/')}/internal/stores/{store_id}/vision-raw",
        data=body,
        method="POST",
        headers={
            **_headers(api_key),
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        response.read()


def post_empty_ingest(api: str, api_key: str | None, store_id: str, frame_index: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    camera_id = f"{store_id}-cam1"
    frame_id = f"upload-{frame_index:04d}"
    post_json(
        api,
        api_key,
        "/internal/store-states",
        {
            "schema_version": "1.0",
            "store_id": store_id,
            "camera_id": camera_id,
            "frame_id": frame_id,
            "captured_at": now,
            "visible_person_count": 0,
            "queue_count_estimate": 0,
            "zone_counts": {},
            "quality_status": "unknown",
            "source": "upload_ingest",
            "model_version": "upload-worker-v1",
        },
    )
    post_json(
        api,
        api_key,
        f"/internal/stores/{store_id}/occupancy",
        {
            "schema_version": "1.0",
            "store_id": store_id,
            "camera_id": camera_id,
            "frame_id": frame_id,
            "mode": "live",
            "captured_at": now,
            "source": "upload_ingest",
            "model_version": "upload-worker-v1",
            "coordinate_space": "normalized_image",
            "agents": [],
        },
    )


def extract_frames(media_bytes: bytes, media_type: str, workdir: Path) -> list[Path]:
    frames_dir = workdir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    max_frames = int(os.getenv("AISEYE_UPLOAD_MAX_FRAMES", "120"))
    if media_type == "frames_zip":
        with zipfile.ZipFile(io.BytesIO(media_bytes)) as archive:
            names = sorted(
                name
                for name in archive.namelist()
                if name.lower().endswith((".jpg", ".jpeg", ".png"))
                and not name.startswith("__MACOSX")
            )
            if not names:
                raise ValueError("ZIP에 JPEG/PNG 프레임이 없습니다.")
            paths = []
            for index, name in enumerate(names[:max_frames]):
                target = frames_dir / f"{index:04d}{Path(name).suffix.lower()}"
                target.write_bytes(archive.read(name))
                paths.append(target)
            return paths

    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "영상 처리에 OpenCV가 필요합니다. pip install opencv-python-headless "
            "또는 프레임 ZIP을 업로드하세요."
        ) from exc

    video_path = workdir / "source.mp4"
    video_path.write_bytes(media_bytes)
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError("영상을 열 수 없습니다.")
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    step = max(1, total // max_frames) if total > 0 else 15
    paths: list[Path] = []
    index = 0
    saved = 0
    while saved < max_frames:
        ok, frame = capture.read()
        if not ok:
            break
        if index % step == 0:
            target = frames_dir / f"{saved:04d}.jpg"
            cv2.imwrite(str(target), frame)
            paths.append(target)
            saved += 1
        index += 1
    capture.release()
    if not paths:
        raise ValueError("영상에서 프레임을 추출하지 못했습니다.")
    return paths


def resolve_cafe_model() -> Path | None:
    configured = os.getenv("AISEYE_CAFE_MODEL", "").strip()
    candidates = [
        Path(configured) if configured else None,
        Path(DEFAULT_CAFE_MODEL),
        WORKER_DIR.parents[1] / "best.pt",
    ]
    for path in candidates:
        if path is not None and path.is_file():
            return path
    return None


class CafeUploadTracker:
    """best.pt + ByteTrack으로 업로드 프레임을 추적하고 occupancy를 만든다."""

    def __init__(self, api: str, model_path: Path) -> None:
        os.environ.setdefault("AISEYE_API_BASE_URL", api)
        os.environ.setdefault("AISEYE_CAFE_MODEL", str(model_path))

        import cv2
        import numpy as np
        from ultralytics import YOLO

        from cafe_stores import (
            DETECTION_CONFIDENCE,
            MODEL_VERSION,
            TRACKER_CONFIG,
            person_positions,
            runtime_roi_identity,
            runtime_zones,
            staff_candidates,
        )
        from cafe_tracking import TrackingEpoch, reset_ultralytics_tracker
        from replay_states import prepare_occupancy
        from roi_zone_counter import build_store_state

        self.cv2 = cv2
        self.np = np
        self.DETECTION_CONFIDENCE = DETECTION_CONFIDENCE
        self.TRACKER_CONFIG = TRACKER_CONFIG
        self.MODEL_VERSION = MODEL_VERSION
        self.person_positions = person_positions
        self.runtime_zones = runtime_zones
        self.runtime_roi_identity = runtime_roi_identity
        self.staff_candidates = staff_candidates
        self.TrackingEpoch = TrackingEpoch
        self.reset_ultralytics_tracker = reset_ultralytics_tracker
        self.prepare_occupancy = prepare_occupancy
        self.build_store_state = build_store_state
        self.YOLO = YOLO
        self.model_path = model_path
        self._models: dict[str, YOLO] = {}
        self._models_lock = threading.Lock()
        print(f"[tracker] loaded {model_path} conf={DETECTION_CONFIDENCE} tracker={TRACKER_CONFIG}")

    def get_model(self, store_id: str):
        with self._models_lock:
            if store_id not in self._models:
                print(f"[tracker] initializing YOLO model instance for {store_id}")
                self._models[store_id] = self.YOLO(str(self.model_path))
            return self._models[store_id]

    def analyze_frames(
        self,
        api: str,
        api_key: str | None,
        store_id: str,
        frames: list[Path],
        *,
        play_interval: float = 0.02,
        loop_forever: bool = False,
        cycle: int = 0,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> None:
        camera_id = f"{store_id}-cam1"
        epoch = self.TrackingEpoch(camera_id)
        empty_pose = {"waiting": [], "seated": []}
        cycle_index = cycle
        ft_model = self.get_model(store_id)

        while True:
            epoch.reset()
            self.reset_ultralytics_tracker(ft_model)
            print(
                f"[tracker] play store={store_id} cycle={cycle_index} "
                f"frames={len(frames)} interval={play_interval}s"
            )
            for index, frame_path in enumerate(frames):
                frame = self.cv2.imread(str(frame_path))
                if frame is None:
                    print(f"[tracker] skip unreadable frame {frame_path.name}")
                    continue
                height, width = frame.shape[:2]
                zones = self.runtime_zones(store_id, camera_id, width, height)
                roi_version, _roi_source = self.runtime_roi_identity(
                    store_id, camera_id, width, height
                )

                result = ft_model.track(
                    frame,
                    persist=True,
                    tracker=self.TRACKER_CONFIG,
                    classes=[0],
                    conf=self.DETECTION_CONFIDENCE,
                    iou=0.5,
                    agnostic_nms=True,
                    verbose=False,
                )[0]
                boxes = (
                    result.boxes.xyxy.cpu().numpy()
                    if result.boxes is not None
                    else self.np.empty((0, 4))
                )
                confidences = (
                    result.boxes.conf.cpu().numpy().tolist()
                    if result.boxes is not None
                    else []
                )
                local_ids = (
                    result.boxes.id.cpu().numpy().astype(int).tolist()
                    if result.boxes is not None and result.boxes.id is not None
                    else [None] * len(boxes)
                )
                public_ids = [
                    epoch.public_id(track_id) if track_id is not None else None
                    for track_id in local_ids
                ]
                staff_flags = self.staff_candidates(boxes, zones, store_id)
                positions = self.person_positions(
                    boxes,
                    zones,
                    empty_pose,
                    public_ids,
                    confidences,
                    staff_flags,
                )
                customers = sum(
                    1 for position in positions if position.get("type") != "staff"
                )
                staff = sum(
                    1 for position in positions if position.get("type") == "staff"
                )
                waiting = sum(
                    1
                    for position in positions
                    if position.get("state") == "queue"
                    or position.get("zone") == "waiting"
                )

                now = datetime.now(timezone.utc)
                frame_id = f"upload-c{cycle_index}-f{index:04d}"
                state = self.build_store_state(
                    {"staff": staff, "waiting": waiting},
                    customers,
                    waiting,
                    camera_id=camera_id,
                    store_id=store_id,
                    quality="normal",
                    captured_at=now,
                )
                state.update(
                    {
                        "frame_id": frame_id,
                        "processed_at": now.isoformat(),
                        "roi_version": roi_version,
                        "source": "upload_worker_track",
                        "model_version": self.MODEL_VERSION,
                        "tracking_epoch": epoch.value,
                        "tracking_reset": index == 0,
                        "positions": positions,
                    }
                )
                occupancy = self.prepare_occupancy(
                    state,
                    preserve_timestamp=True,
                    frame_width=width,
                    frame_height=height,
                )
                occupancy["source"] = "upload_worker_track"
                occupancy["model_version"] = self.MODEL_VERSION
                occupancy["published_at"] = now.isoformat()

                try:
                    post_snapshot(api, api_key, store_id, frame_path.read_bytes())
                except Exception as exc:  # noqa: BLE001
                    print(f"[tracker] snapshot warn@{index}: {exc}")

                post_json(api, api_key, "/internal/store-states", state)
                post_json(
                    api,
                    api_key,
                    f"/internal/stores/{store_id}/occupancy",
                    occupancy,
                )

                if index % 5 == 0 or index + 1 == len(frames):
                    if on_progress is not None:
                        on_progress(index + 1, len(frames), f"YOLOv11s 객체 추적 중 ({index + 1}/{len(frames)})")

                if index % 10 == 0 or index + 1 == len(frames):
                    print(
                        f"[tracker] [{store_id}] c{cycle_index} {index + 1}/{len(frames)} "
                        f"people={customers} staff={staff} "
                        f"agents={len(occupancy.get('agents', []))}"
                    )
                time.sleep(max(play_interval, 0.0))

            if not loop_forever:
                return
            cycle_index += 1


def cache_frames(store_id: str, frames: list[Path]) -> Path:
    target_dir = REPLAY_CACHE_DIR / store_id
    target_dir.mkdir(parents=True, exist_ok=True)
    for old in target_dir.glob("*"):
        if old.is_file():
            old.unlink()
    cached: list[Path] = []
    for index, frame_path in enumerate(frames):
        dest = target_dir / f"{index:04d}{frame_path.suffix.lower()}"
        dest.write_bytes(frame_path.read_bytes())
        cached.append(dest)
    meta = target_dir / "meta.json"
    meta.write_text(
        json.dumps({"store_id": store_id, "frames": len(cached)}, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[replay-cache] saved {len(cached)} frames → {target_dir}")
    return target_dir


def load_cached_frames(store_id: str) -> list[Path]:
    target_dir = REPLAY_CACHE_DIR / store_id
    frames = sorted(
        [
            path
            for path in target_dir.iterdir()
            if path.suffix.lower() in {".jpg", ".jpeg", ".png"}
        ]
    )
    if not frames:
        raise FileNotFoundError(
            f"재생 캐시 없음: {target_dir}. 먼저 analysis job을 한 번 처리하세요."
        )
    return frames


def process_claim(
    api: str,
    api_key: str | None,
    claim: dict,
    tracker: CafeUploadTracker | None,
    *,
    play_interval: float = 0.02,
) -> str:
    """Process one job. Returns store_id for optional auto-replay."""
    job = claim["job"]
    media = claim["media"]
    job_id = job["id"]
    store_id = job["store_id"]
    download_url = f"{api.rstrip('/')}{claim['download_path']}"
    print(f"[job {job_id}] claim store={store_id} media={media['filename']}")
    patch_job(
        api,
        api_key,
        job_id,
        "running",
        progress_percent=5.0,
        stage_message="미디어 영상 다운로드 및 프레임 추출 중...",
    )
    media_bytes = http_bytes(download_url, api_key)
    with tempfile.TemporaryDirectory(prefix="aiseeye-job-") as tmp:
        frames = extract_frames(media_bytes, media["media_type"], Path(tmp))
        cache_frames(store_id, frames)
        patch_job(
            api,
            api_key,
            job_id,
            "running",
            progress_percent=15.0,
            processed_frames=0,
            total_frames=len(frames),
            stage_message=f"프레임 {len(frames)}개 추출 완료 · YOLOv11s 분석 준비",
        )

        def report_progress(current_frame: int, total_f: int, msg: str):
            pct = 15.0 + (current_frame / max(total_f, 1)) * 80.0
            patch_job(
                api,
                api_key,
                job_id,
                "running",
                progress_percent=min(pct, 98.0),
                processed_frames=current_frame,
                total_frames=total_f,
                stage_message=msg,
            )

        if tracker is not None:
            # One pass to seed state/occupancy quickly, then auto-replay thread loops.
            tracker.analyze_frames(
                api,
                api_key,
                store_id,
                frames,
                play_interval=min(play_interval, 0.05),
                loop_forever=False,
                on_progress=report_progress,
            )
        else:
            print("[job] AISEYE_CAFE_MODEL 없음 → empty ingest")
            try:
                post_snapshot(api, api_key, store_id, frames[0].read_bytes())
            except Exception as exc:  # noqa: BLE001
                print(f"[job {job_id}] snapshot warn: {exc}")
            for index, frame_path in enumerate(frames):
                if index > 0 and index % 10 == 0:
                    try:
                        post_snapshot(api, api_key, store_id, frame_path.read_bytes())
                    except Exception as exc:  # noqa: BLE001
                        print(f"[job {job_id}] snapshot warn@{index}: {exc}")
                post_empty_ingest(api, api_key, store_id, index)
                if index % 5 == 0 or index + 1 == len(frames):
                    report_progress(index + 1, len(frames), f"프레임 수집 중 ({index + 1}/{len(frames)})")
                time.sleep(0.05)
    patch_job(
        api,
        api_key,
        job_id,
        "completed",
        progress_percent=100.0,
        processed_frames=len(frames),
        total_frames=len(frames),
        stage_message="CCTV 영상 분석 완료",
    )
    print(f"[job {job_id}] completed frames={len(frames)}")
    return store_id


class AutoReplayManager:
    """매장별 재생 스레드. 온보딩 job 완료 후/워커 기동 시 캐시를 루프한다."""

    def __init__(
        self,
        *,
        api: str,
        api_key: str | None,
        tracker: CafeUploadTracker,
        play_interval: float,
    ) -> None:
        self.api = api
        self.api_key = api_key
        self.tracker = tracker
        self.play_interval = play_interval
        self._stops: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    def stop_store(self, store_id: str) -> None:
        thread: threading.Thread | None = None
        with self._lock:
            previous = self._stops.get(store_id)
            thread = self._threads.get(store_id)
            if previous is not None:
                previous.set()
        if thread is not None and thread.is_alive():
            thread.join(timeout=max(self.play_interval * 3, 5.0))

    def stop_all(self) -> None:
        """다른 매장 재생 스레드가 tracker lock을 잡지 않도록 모두 멈춘다."""
        with self._lock:
            store_ids = list(self._threads)
        for store_id in store_ids:
            self.stop_store(store_id)

    def start_store(self, store_id: str) -> None:
        self.stop_store(store_id)
        with self._lock:
            stop = threading.Event()
            self._stops[store_id] = stop
            thread = threading.Thread(
                target=self._run_store,
                args=(store_id, stop),
                name=f"replay-{store_id}",
                daemon=True,
            )
            self._threads[store_id] = thread
            thread.start()
            print(f"[auto-replay] started {store_id}")

    def resume_cached_stores(self) -> None:
        if not REPLAY_CACHE_DIR.is_dir():
            return
        for path in sorted(REPLAY_CACHE_DIR.iterdir()):
            if not path.is_dir():
                continue
            try:
                load_cached_frames(path.name)
            except FileNotFoundError:
                continue
            self.start_store(path.name)

    def _run_store(self, store_id: str, stop: threading.Event) -> None:
        try:
            frames = load_cached_frames(store_id)
        except FileNotFoundError as exc:
            print(f"[auto-replay] {exc}")
            return
        cycle = 0
        while not stop.is_set():
            try:
                self.tracker.analyze_frames(
                    self.api,
                    self.api_key,
                    store_id,
                    frames,
                    play_interval=self.play_interval,
                    loop_forever=False,
                    cycle=cycle,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[auto-replay] {store_id} error: {exc}")
                time.sleep(2)
            cycle += 1


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload analysis job GPU worker")
    parser.add_argument("--api", default=os.getenv("AISEYE_API", "http://127.0.0.1:8000"))
    parser.add_argument("--api-key", default=os.getenv("INTERNAL_API_KEY"))
    parser.add_argument("--worker-id", default=os.getenv("HOSTNAME", "gpu-worker"))
    parser.add_argument("--loop", action="store_true", help="Keep polling for new jobs")
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Job poll interval when --loop (seconds)",
    )
    parser.add_argument(
        "--play-interval",
        type=float,
        default=float(os.getenv("AISEYE_UPLOAD_PLAY_INTERVAL", "1.0")),
        help="Delay between posted frames during track/replay (seconds)",
    )
    parser.add_argument(
        "--replay-store",
        default=os.getenv("AISEYE_UPLOAD_REPLAY_STORE", ""),
        help="Loop cached frames for this store_id (demo playback)",
    )
    parser.add_argument(
        "--auto-replay",
        action=argparse.BooleanOptionalAction,
        default=_env_flag("AISEYE_UPLOAD_AUTO_REPLAY", True),
        help="After jobs (and on startup) loop cached stores in background",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("AISEYE_CAFE_MODEL", ""),
        help="CAFE fine-tuned YOLO weights (enables tracking)",
    )
    args = parser.parse_args()

    if args.model:
        os.environ["AISEYE_CAFE_MODEL"] = args.model
    os.environ.setdefault("AISEYE_API_BASE_URL", args.api)
    if args.api_key:
        os.environ.setdefault("INTERNAL_API_KEY", args.api_key)

    model_path = Path(args.model) if args.model else resolve_cafe_model()
    tracker: CafeUploadTracker | None = None
    if model_path is not None:
        try:
            tracker = CafeUploadTracker(args.api, model_path)
        except Exception as exc:  # noqa: BLE001
            print(f"[tracker] init failed, falling back to empty ingest: {exc}")
            tracker = None
    else:
        print("[tracker] no CAFE model → empty ingest mode")

    if args.replay_store:
        if tracker is None:
            print("--replay-store 에는 AISEYE_CAFE_MODEL 이 필요합니다", file=sys.stderr)
            return 1
        frames = load_cached_frames(args.replay_store)
        try:
            tracker.analyze_frames(
                args.api,
                args.api_key,
                args.replay_store,
                frames,
                play_interval=args.play_interval,
                loop_forever=True,
            )
        except KeyboardInterrupt:
            return 0
        return 0

    replay_manager: AutoReplayManager | None = None
    if args.auto_replay and tracker is not None:
        replay_manager = AutoReplayManager(
            api=args.api,
            api_key=args.api_key,
            tracker=tracker,
            play_interval=args.play_interval,
        )
        replay_manager.resume_cached_stores()

    while True:
        try:
            try:
                claim = claim_job(args.api, args.api_key, args.worker_id)
            except Exception as exc:  # noqa: BLE001
                print(f"[worker-poll] claim_job error (will retry in {args.interval}s): {exc}")
                if not args.loop:
                    return 1
                time.sleep(args.interval)
                continue

            if claim is None:
                if not args.loop:
                    print("queued job 없음")
                    return 0
                time.sleep(args.interval)
                continue
            try:
                store_id = claim["job"]["store_id"]
                if replay_manager is not None:
                    replay_manager.stop_all()
                store_id = process_claim(
                    args.api,
                    args.api_key,
                    claim,
                    tracker,
                    play_interval=args.play_interval,
                )
                if replay_manager is not None:
                    replay_manager.start_store(store_id)
            except Exception as exc:  # noqa: BLE001
                print(f"job failed: {exc}")
                patch_job(args.api, args.api_key, claim["job"]["id"], "failed", str(exc))
                if not args.loop:
                    return 1
        except KeyboardInterrupt:
            return 0
        if not args.loop:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
