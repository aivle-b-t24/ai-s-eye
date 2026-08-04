#!/usr/bin/env python3
"""업로드형 온보딩 분석 job을 가져와 state/snapshot을 API에 올리는 GPU 워커.

미니PC API(Tailscale) + INTERNAL_API_KEY 로 동작한다.

  export AISEYE_API=http://100.x.x.x:8000
  export INTERNAL_API_KEY=...
  python upload_job_worker.py --loop

모델 가중치가 없어도 프레임 추출 + 빈(ingest) state를 올려 파이프라인을 검증할 수 있다.
YOLO 추적은 AISEYE_CAFE_MODEL 이 있을 때 확장하면 된다.
"""

from __future__ import annotations

import argparse
import io
import os
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import urllib.error
import urllib.request


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
        import json

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


def patch_job(api: str, api_key: str | None, job_id: str, status: str, error: str | None = None):
    import json

    payload = {"status": status, "worker_id": os.getenv("HOSTNAME", "gpu-worker")}
    if error:
        payload["error_message"] = error
    http_json(
        "PATCH",
        f"{api.rstrip('/')}/internal/analysis-jobs/{job_id}",
        api_key,
        json.dumps(payload).encode("utf-8"),
    )


def post_state(api: str, api_key: str | None, store_id: str, frame_index: int) -> None:
    import json

    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": "1.0",
        "store_id": store_id,
        "camera_id": f"{store_id}-cam1",
        "frame_id": f"upload-{frame_index:04d}",
        "captured_at": now,
        "visible_person_count": 0,
        "queue_count_estimate": 0,
        "zone_counts": {},
        "quality_status": "unknown",
        "source": "upload_ingest",
        "model_version": "upload-worker-v1",
    }
    http_json(
        "POST",
        f"{api.rstrip('/')}/internal/store-states",
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


def post_occupancy(
    api: str,
    api_key: str | None,
    store_id: str,
    frame_index: int,
) -> None:
    import json

    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": "1.0",
        "store_id": store_id,
        "camera_id": f"{store_id}-cam1",
        "frame_id": f"upload-{frame_index:04d}",
        "mode": "live",
        "captured_at": now,
        "source": "upload_ingest",
        "model_version": "upload-worker-v1",
        "coordinate_space": "normalized_image",
        "agents": [],
    }
    http_json(
        "POST",
        f"{api.rstrip('/')}/internal/stores/{store_id}/occupancy",
        api_key,
        json.dumps(payload).encode("utf-8"),
    )


def extract_frames(media_bytes: bytes, media_type: str, workdir: Path) -> list[Path]:
    frames_dir = workdir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
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
            for index, name in enumerate(names[:120]):
                target = frames_dir / f"{index:04d}{Path(name).suffix.lower()}"
                target.write_bytes(archive.read(name))
                paths.append(target)
            return paths

    # video — OpenCV 사용 (없으면 실패로 보고 수동 ZIP 권장)
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
    step = max(1, total // 60) if total > 0 else 15
    paths: list[Path] = []
    index = 0
    saved = 0
    while saved < 60:
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


def process_claim(api: str, api_key: str | None, claim: dict) -> None:
    job = claim["job"]
    media = claim["media"]
    job_id = job["id"]
    store_id = job["store_id"]
    download_url = f"{api.rstrip('/')}{claim['download_path']}"
    print(f"[job {job_id}] claim store={store_id} media={media['filename']}")
    media_bytes = http_bytes(download_url, api_key)
    with tempfile.TemporaryDirectory(prefix="aiseeye-job-") as tmp:
        frames = extract_frames(media_bytes, media["media_type"], Path(tmp))
        first = frames[0].read_bytes()
        # Prefer a JPEG for vision-raw; convert PNG first frame if needed later.
        try:
            post_snapshot(api, api_key, store_id, first)
        except Exception as exc:  # noqa: BLE001 — 스냅샷 실패해도 state는 시도
            print(f"[job {job_id}] snapshot warn: {exc}")
        for index, frame_path in enumerate(frames):
            if index > 0 and index % 10 == 0:
                try:
                    post_snapshot(api, api_key, store_id, frame_path.read_bytes())
                except Exception as exc:  # noqa: BLE001
                    print(f"[job {job_id}] snapshot warn@{index}: {exc}")
            post_state(api, api_key, store_id, index)
            try:
                post_occupancy(api, api_key, store_id, index)
            except Exception as exc:  # noqa: BLE001
                print(f"[job {job_id}] occupancy warn@{index}: {exc}")
            time.sleep(0.05)
    patch_job(api, api_key, job_id, "completed")
    print(f"[job {job_id}] completed frames={len(frames)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload analysis job GPU worker")
    parser.add_argument("--api", default=os.getenv("AISEYE_API", "http://127.0.0.1:8000"))
    parser.add_argument("--api-key", default=os.getenv("INTERNAL_API_KEY"))
    parser.add_argument("--worker-id", default=os.getenv("HOSTNAME", "gpu-worker"))
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args()

    while True:
        try:
            claim = claim_job(args.api, args.api_key, args.worker_id)
            if claim is None:
                if not args.loop:
                    print("queued job 없음")
                    return 0
                time.sleep(args.interval)
                continue
            try:
                process_claim(args.api, args.api_key, claim)
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
