"""분석 결과(JSON)를 API로 순서대로 재생 전송한다.

이미지·YOLO·GPU 없이 동작한다. 미리 분석해 둔 store_state 목록을 읽어
일정 간격으로 POST 하므로, 대시보드에서 혼잡도가 실시간처럼 변한다.

필요한 것: 결과 JSON 파일 + 실행 중인 API. (파이썬 표준 라이브러리만 사용)

실행:
    py services/vision-worker/replay_states.py
    py services/vision-worker/replay_states.py --interval 1 --limit 100
    py services/vision-worker/replay_states.py --file samples/store_states_timeseries.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FILE = REPO_ROOT / "samples" / "cafe_stores_states.json"
DEFAULT_FRAME_WIDTH = 1920
DEFAULT_FRAME_HEIGHT = 1080
DEFAULT_ROI_REFRESH_SECONDS = 2.0
ROI_ZONE_PRIORITY = ("staff", "waiting", "seating", "entrance")


def internal_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = dict(extra or {})
    key = os.getenv("INTERNAL_API_KEY")
    if key:
        headers["X-Internal-API-Key"] = key
    return headers


def fetch_approved_roi_config(
    api_base_url: str,
    store_id: str,
    camera_id: str,
    timeout: float = 3.0,
) -> dict:
    """API에서 현재 승인된 ROI 설정을 읽는다."""
    url = (
        api_base_url.rstrip("/")
        + f"/internal/stores/{store_id}/cameras/{camera_id}/roi-config"
    )
    request = urllib.request.Request(
        url,
        headers=internal_headers({"Accept": "application/json"}),
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _point_on_segment(
    point: tuple[float, float],
    first: tuple[float, float],
    second: tuple[float, float],
    epsilon: float = 1e-6,
) -> bool:
    px, py = point
    ax, ay = first
    bx, by = second
    cross = (px - ax) * (by - ay) - (py - ay) * (bx - ax)
    if abs(cross) > epsilon:
        return False
    return (
        min(ax, bx) - epsilon <= px <= max(ax, bx) + epsilon
        and min(ay, by) - epsilon <= py <= max(ay, by) + epsilon
    )


def point_in_polygon(
    point: tuple[float, float],
    polygon: list[dict],
) -> bool:
    """경계선을 포함해 점이 폴리곤 안에 있는지 계산한다."""
    if len(polygon) < 3:
        return False
    vertices = [
        (float(vertex["x"]), float(vertex["y"]))
        for vertex in polygon
    ]
    inside = False
    previous = vertices[-1]
    for current in vertices:
        if _point_on_segment(point, previous, current):
            return True
        x1, y1 = previous
        x2, y2 = current
        intersects = (
            (y1 > point[1]) != (y2 > point[1])
            and point[0]
            < (x2 - x1) * (point[1] - y1) / (y2 - y1) + x1
        )
        if intersects:
            inside = not inside
        previous = current
    return inside


def normalized_roi_point(
    position: dict,
    *,
    frame_width: int,
    frame_height: int,
) -> tuple[float, float]:
    """픽셀 발 좌표를 ROI의 0~1000 좌표계로 바꾼다."""
    if frame_width <= 0 or frame_height <= 0:
        raise ValueError("Frame dimensions must be greater than zero")
    return (
        min(max(float(position.get("x", 0)) / frame_width * 1000, 0), 1000),
        min(max(float(position.get("y", 0)) / frame_height * 1000, 0), 1000),
    )


def position_zone(
    position: dict,
    config: dict,
    *,
    frame_width: int = DEFAULT_FRAME_WIDTH,
    frame_height: int = DEFAULT_FRAME_HEIGHT,
) -> str | None:
    """현재 승인 ROI를 기준으로 사람의 구역을 다시 결정한다."""
    point = normalized_roi_point(
        position,
        frame_width=frame_width,
        frame_height=frame_height,
    )
    zones = config.get("zones", [])
    for zone_type in ROI_ZONE_PRIORITY:
        for zone in zones:
            if zone.get("type") != zone_type:
                continue
            if point_in_polygon(point, zone.get("polygon", [])):
                return zone_type
    return None


def reclassify_state_for_roi(
    state: dict,
    config: dict,
    *,
    processed_at: datetime | None = None,
    frame_width: int = DEFAULT_FRAME_WIDTH,
    frame_height: int = DEFAULT_FRAME_HEIGHT,
) -> dict:
    """저장된 YOLO·Tracking 좌표를 현재 승인 ROI로 다시 판정한다.

    사람 탐지와 track_id는 기존 Vision 결과를 유지하고, ROI에 의존하는
    zone·role·state와 StoreState 집계만 새 승인 버전으로 재생성한다.
    """
    result = {
        **state,
        "positions": [],
        "zone_counts": {},
    }
    zone_counts = {
        zone_type: 0
        for zone_type in ROI_ZONE_PRIORITY
        if any(
            zone.get("type") == zone_type
            for zone in config.get("zones", [])
        )
    }
    staff_count = 0
    queue_count = 0

    for original in state.get("positions", []):
        position = original.copy()
        zone = position_zone(
            position,
            config,
            frame_width=frame_width,
            frame_height=frame_height,
        )
        position["zone"] = zone
        if zone is not None:
            zone_counts[zone] = zone_counts.get(zone, 0) + 1

        if zone == "staff":
            position["type"] = "staff"
            position["state"] = "working"
            staff_count += 1
        elif zone == "waiting":
            position["type"] = "customer"
            position["state"] = "queue"
            queue_count += 1
        elif zone == "seating":
            position["type"] = "customer"
            position["state"] = (
                "seated"
                if original.get("state") == "seated"
                else "unknown"
            )
        elif zone == "entrance":
            position["type"] = "customer"
            position["state"] = (
                original.get("state")
                if original.get("state") in {"entering", "exiting"}
                else "unknown"
            )
        else:
            position["type"] = "customer"
            position["state"] = "unknown"
        result["positions"].append(position)

    result["visible_person_count"] = max(
        len(result["positions"]) - staff_count,
        0,
    )
    result["queue_count_estimate"] = queue_count
    result["zone_counts"] = zone_counts
    result["roi_version"] = config.get("version")
    result["processed_at"] = (
        processed_at or datetime.now(timezone.utc)
    ).isoformat()
    result["source"] = "vision-worker-roi-replay"
    return result


class RoiConfigProvider:
    """승인 ROI를 짧게 캐시하고 버전 변경을 감지한다."""

    def __init__(
        self,
        api_base_url: str,
        refresh_seconds: float = DEFAULT_ROI_REFRESH_SECONDS,
    ) -> None:
        self.api_base_url = api_base_url
        self.refresh_seconds = max(refresh_seconds, 0.0)
        self._cache: dict[tuple[str, str], dict] = {}
        self._checked_at: dict[tuple[str, str], float] = {}

    def get(self, store_id: str, camera_id: str) -> dict | None:
        key = (store_id, camera_id)
        now = time.monotonic()
        last_checked = self._checked_at.get(key)
        if (
            key in self._cache
            and last_checked is not None
            and now - last_checked < self.refresh_seconds
        ):
            return self._cache[key]

        self._checked_at[key] = now
        try:
            config = fetch_approved_roi_config(
                self.api_base_url,
                store_id,
                camera_id,
            )
        except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError):
            return self._cache.get(key)

        previous = self._cache.get(key)
        self._cache[key] = config
        if previous is None:
            print(
                f"  ROI 적용 {store_id}/{camera_id}: "
                f"v{config.get('version', '?')}"
            )
        elif previous.get("version") != config.get("version"):
            print(
                f"  ROI 갱신 {store_id}/{camera_id}: "
                f"v{previous.get('version', '?')} -> "
                f"v{config.get('version', '?')}"
            )
        return config


class LegacyPositionTracker:
    """track_id가 없는 이전 좌표 JSON에 재생 중 임시 ID를 부여한다.

    새 Vision 결과는 ByteTrack ID를 그대로 사용한다. 이 추적기는 기존 804건
    샘플을 다시 분석하기 전에도 프론트의 배열 인덱스가 사람 ID로 오인되는
    현상을 막기 위한 호환 계층이다.
    """

    def __init__(self, max_distance: float = 160.0, max_missed: int = 3):
        self.max_distance = max_distance
        self.max_missed = max_missed
        self._next_id = 1
        self._tracks: dict[str, dict[str, float | int]] = {}

    def reset_active(self) -> None:
        """반복 재생 경계에서 이전 마지막 프레임과 첫 프레임을 잇지 않는다."""
        self._tracks.clear()

    def assign(self, positions: list[dict]) -> list[dict]:
        """최근 위치와 속도를 이용해 현재 위치에 안정적인 임시 ID를 연결한다."""
        if not positions:
            for track in self._tracks.values():
                track["missed"] = int(track["missed"]) + 1
            self._prune()
            return []

        output = [position.copy() for position in positions]
        unmatched_positions = {
            index for index, position in enumerate(output)
            if position.get("track_id") is None
        }

        # 새 Vision 결과처럼 명시적인 ID가 있으면 그대로 보존한다.
        if not unmatched_positions:
            return output

        unmatched_tracks = set(self._tracks)
        candidate_pairs = []
        for track_id, track in self._tracks.items():
            predicted_x = float(track["x"]) + float(track["vx"])
            predicted_y = float(track["y"]) + float(track["vy"])
            for index in unmatched_positions:
                position = output[index]
                current_x = float(position.get("x", 0))
                current_y = float(position.get("y", 0))
                distance = math.hypot(
                    current_x - predicted_x,
                    current_y - predicted_y,
                )
                movement = math.hypot(
                    current_x - float(track["x"]),
                    current_y - float(track["y"]),
                )
                if distance <= self.max_distance and movement <= self.max_distance:
                    candidate_pairs.append((distance, track_id, index))

        for _, track_id, index in sorted(candidate_pairs):
            if track_id not in unmatched_tracks or index not in unmatched_positions:
                continue
            position = output[index]
            track = self._tracks[track_id]
            new_x = float(position.get("x", 0))
            new_y = float(position.get("y", 0))
            track["vx"] = new_x - float(track["x"])
            track["vy"] = new_y - float(track["y"])
            track["x"] = new_x
            track["y"] = new_y
            track["missed"] = 0
            position["track_id"] = track_id
            unmatched_tracks.remove(track_id)
            unmatched_positions.remove(index)

        for track_id in unmatched_tracks:
            self._tracks[track_id]["missed"] = (
                int(self._tracks[track_id]["missed"]) + 1
            )

        for index in sorted(unmatched_positions):
            position = output[index]
            track_id = f"legacy-{self._next_id}"
            self._next_id += 1
            position["track_id"] = track_id
            self._tracks[track_id] = {
                "x": float(position.get("x", 0)),
                "y": float(position.get("y", 0)),
                "vx": 0.0,
                "vy": 0.0,
                "missed": 0,
            }

        self._prune()
        return output

    def _prune(self) -> None:
        expired = [
            track_id for track_id, track in self._tracks.items()
            if int(track["missed"]) > self.max_missed
        ]
        for track_id in expired:
            del self._tracks[track_id]


def load_states(path: Path) -> list[dict]:
    """결과 파일 → store_state 목록. 배열/객체 두 형식 모두 지원."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "states" in data:
        # {"states": [{"frame": n, "state": {...}}, ...]} 형식
        return [s["state"] if "state" in s else s for s in data["states"]]
    if isinstance(data, list):
        return [s["state"] if isinstance(s, dict) and "state" in s else s for s in data]
    return [data]  # 단건


def group_states_by_tick(states: list[dict]) -> list[list[dict]]:
    """매장별 같은 순번의 상태를 하나의 재생 시점으로 묶는다.

    입력 순서가 매장별로 섞여 있어도 각 매장의 0번, 1번 상태가 같은 묶음에
    들어간다. 매장별 데이터 길이가 다르면 남은 상태는 단독 묶음으로 재생한다.
    """
    store_order: list[str] = []
    states_by_store: dict[str, list[dict]] = {}
    for state in states:
        store_id = state["store_id"]
        if store_id not in states_by_store:
            store_order.append(store_id)
            states_by_store[store_id] = []
        states_by_store[store_id].append(state)

    if not store_order:
        return []

    tick_count = max(len(items) for items in states_by_store.values())
    return [
        [
            states_by_store[store_id][index]
            for store_id in store_order
            if index < len(states_by_store[store_id])
        ]
        for index in range(tick_count)
    ]


def post_state(url: str, state: dict, timeout: float = 5.0) -> int:
    body = json.dumps(state).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers=internal_headers({"Content-Type": "application/json"}),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status


def post_snapshot(
    api: str,
    store_id: str,
    image_bytes: bytes,
    timeout: float = 10.0,
    *,
    raw: bool = False,
    metadata: dict | None = None,
) -> int:
    """분석본 또는 ROI 설정용 원본 이미지를 API에 업로드한다."""
    boundary = "----visionsnapshotboundary"
    parts = []
    if metadata is not None:
        parts.append(
            f"--{boundary}\r\n".encode()
            + b'Content-Disposition: form-data; name="metadata"\r\n'
            + b"Content-Type: application/json\r\n\r\n"
            + json.dumps(metadata, ensure_ascii=False).encode("utf-8")
            + b"\r\n"
        )
    parts.append(
        f"--{boundary}\r\n".encode()
        + b'Content-Disposition: form-data; name="image"; filename="snapshot.jpg"\r\n'
        + b"Content-Type: image/jpeg\r\n\r\n"
        + image_bytes
        + b"\r\n"
    )
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    endpoint = "vision-raw" if raw else "vision-snapshot"
    url = api.rstrip("/") + f"/internal/stores/{store_id}/{endpoint}"
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers=internal_headers({
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status


def prepare_state(
    state: dict,
    *,
    preserve_timestamp: bool = False,
    captured_at: datetime | None = None,
) -> dict:
    """전송할 상태를 복사한다.

    프레임의 분석 신원을 보존하기 위해 신규 산출물은 원래 captured_at을 유지한다.
    frame_id가 없는 이전 샘플만 기존 동작대로 재생 시각을 사용한다.
    """
    outgoing = state.copy()
    for internal_key in (
        "positions",
        "source_seconds",
        "tracking_epoch",
        "tracking_reset",
    ):
        outgoing.pop(internal_key, None)
    if not preserve_timestamp and not outgoing.get("frame_id"):
        current = captured_at or datetime.now(timezone.utc)
        outgoing["captured_at"] = current.isoformat()
    outgoing["source"] = "demo-replay"
    return outgoing


def normalize_coordinate(value: float, size: int) -> float:
    """픽셀 좌표를 화면 크기와 무관한 0~1 좌표로 바꾼다."""
    if size <= 0:
        raise ValueError("Frame size must be greater than zero")
    clamped = min(max(float(value), 0.0), float(size - 1))
    return round(clamped / size, 6)


def prepare_occupancy(
    state: dict,
    *,
    preserve_timestamp: bool = False,
    captured_at: datetime | None = None,
    frame_width: int = DEFAULT_FRAME_WIDTH,
    frame_height: int = DEFAULT_FRAME_HEIGHT,
    position_tracker: LegacyPositionTracker | None = None,
    id_prefix: str | None = None,
) -> dict:
    """Vision positions를 LIVE 디지털 트윈 공통 프레임으로 변환한다."""
    if preserve_timestamp or state.get("frame_id"):
        timestamp = state["captured_at"]
    else:
        timestamp = (captured_at or datetime.now(timezone.utc)).isoformat()

    positions = state.get("positions", [])
    if position_tracker is not None:
        positions = position_tracker.assign(positions)

    agents = []
    queue_remaining = max(int(state.get("queue_count_estimate", 0)), 0)
    valid_states = {
        "entering",
        "queue",
        "ordering",
        "waiting",
        "seated",
        "exiting",
        "working",
        "unknown",
    }
    for position in positions:
        role = (
            "staff"
            if position.get("type") == "staff"
            else "customer"
        )
        zone = position.get("zone")
        explicit_state = position.get("state")
        if explicit_state in valid_states:
            agent_state = explicit_state
            if agent_state == "queue" and queue_remaining > 0:
                queue_remaining -= 1
        elif role == "staff":
            agent_state = "working"
        elif zone == "waiting" and queue_remaining > 0:
            agent_state = "queue"
            queue_remaining -= 1
        elif zone == "waiting":
            agent_state = "waiting"
        else:
            agent_state = "unknown"

        track_id = position.get("track_id")
        agent_id = str(track_id) if track_id is not None else None
        if agent_id is not None and id_prefix:
            agent_id = f"{id_prefix}:{agent_id}"
        position_x = normalize_coordinate(position.get("x", 0), frame_width)
        position_y = normalize_coordinate(position.get("y", 0), frame_height)

        agent = {
            "id": agent_id,
            "x": position_x,
            "y": position_y,
            "role": role,
            "state": agent_state,
            "zone": zone,
        }
        bbox = position.get("bbox")
        if isinstance(bbox, dict):
            agent["bbox"] = {
                "x1": normalize_coordinate(bbox.get("x1", 0), frame_width),
                "y1": normalize_coordinate(bbox.get("y1", 0), frame_height),
                "x2": normalize_coordinate(bbox.get("x2", 0), frame_width),
                "y2": normalize_coordinate(bbox.get("y2", 0), frame_height),
            }
        confidence = position.get("confidence")
        if confidence is not None:
            agent["confidence"] = min(max(float(confidence), 0.0), 1.0)
        if position.get("occluded") is not None:
            agent["occluded"] = bool(position["occluded"])
        agents.append(agent)

    store_id = state["store_id"]
    return {
        "schema_version": "1.1",
        "store_id": store_id,
        "camera_id": state.get("camera_id", f"{store_id}-cam1"),
        "frame_id": state.get("frame_id"),
        "mode": "live",
        "captured_at": timestamp,
        "published_at": (captured_at or datetime.now(timezone.utc)).isoformat(),
        "processed_at": state.get("processed_at"),
        "roi_version": state.get("roi_version"),
        "source": "demo-replay",
        "model_version": state.get("model_version"),
        "coordinate_space": "normalized_image",
        "tracking_epoch": state.get("tracking_epoch"),
        "tracking_reset": state.get("tracking_reset"),
        "agents": agents,
    }


def snapshot_metadata(state: dict) -> dict | None:
    """StoreState와 분석 이미지가 공유할 프레임 신원 정보를 만든다."""
    required = (
        "store_id",
        "camera_id",
        "frame_id",
        "captured_at",
        "processed_at",
        "model_version",
        "source",
    )
    if any(state.get(field) in {None, ""} for field in required):
        return None
    return {
        "schema_version": "1.0",
        "store_id": state["store_id"],
        "camera_id": state["camera_id"],
        "frame_id": state["frame_id"],
        "captured_at": state["captured_at"],
        "processed_at": state["processed_at"],
        "model_version": state["model_version"],
        "roi_version": state.get("roi_version"),
        "source": state["source"],
    }


def main():
    ap = argparse.ArgumentParser(description="분석 결과를 API로 재생 전송")
    ap.add_argument("--file", type=Path, default=DEFAULT_FILE, help="결과 JSON 경로")
    ap.add_argument("--api", default="http://localhost:8000", help="API 베이스 URL")
    ap.add_argument("--interval", type=float, default=2.0, help="전송 간격(초)")
    ap.add_argument(
        "--realtime",
        action="store_true",
        help="captured_at 실제 간격대로 프레임별 가변 재생(--interval 대신). "
             "실영상 시간축이면 각 프레임을 실제 경과만큼 대기해 실시간처럼 재생.",
    )
    ap.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="--realtime 배속(2.0=2배 빠르게, 0.5=느리게). 기본 1.0=실시간.",
    )
    ap.add_argument("--limit", type=int, default=None, help="앞에서 N건만 전송")
    ap.add_argument("--loop", action="store_true", help="끝나면 처음부터 반복")
    ap.add_argument(
        "--preserve-timestamps",
        action="store_true",
        help="실시간 재생 대신 JSON의 원본 captured_at을 유지",
    )
    ap.add_argument(
        "--frames-dir",
        type=Path,
        default=None,
        help="상태별 분석 이미지 폴더(frames/{i:04d}.jpg). 지정 시 전송마다 해당 "
             "이미지를 API로 업로드(POST /internal/stores/{id}/vision-snapshot) → 이미지·숫자 동기",
    )
    ap.add_argument(
        "--raw-frames-dir",
        type=Path,
        default=None,
        help="ROI 설정용 원본 이미지 폴더(raw-frames/<store-id>/{i:04d}.jpg). "
             "지정 시 기존 ROI나 탐지 표시가 없는 프레임을 별도로 업로드",
    )
    ap.add_argument(
        "--roi-refresh-seconds",
        type=float,
        default=DEFAULT_ROI_REFRESH_SECONDS,
        help="승인 ROI 재조회 간격(초). 기본 2초",
    )
    ap.add_argument(
        "--no-roi-reclassify",
        action="store_true",
        help="현재 승인 ROI 재판정을 끄고 저장된 zone·role·state를 그대로 재생",
    )
    args = ap.parse_args()

    if not args.file.exists():
        raise SystemExit(f"결과 파일이 없습니다: {args.file}")

    states = load_states(args.file)
    if args.limit:
        states = states[: args.limit]
    state_batches = group_states_by_tick(states)
    # --realtime용: 각 시점의 대표 captured_at(가장 이른 값)을 미리 파싱해 둔다.
    tick_times: list[datetime | None] = []
    for batch in state_batches:
        parsed = []
        for state in batch:
            cap = state.get("captured_at")
            if cap:
                try:
                    parsed.append(datetime.fromisoformat(cap))
                except ValueError:
                    pass
        tick_times.append(min(parsed) if parsed else None)
    state_url = args.api.rstrip("/") + "/internal/store-states"

    print(
        f"재생 시작: {len(states)}건 / {len(state_batches)}시점 / "
        f"간격 {args.interval}초 → {state_url}"
    )
    print("중단하려면 Ctrl+C\n")

    state_sent = occupancy_sent = failed = 0
    position_trackers = {
        store_id: LegacyPositionTracker()
        for store_id in {state["store_id"] for state in states}
    }
    roi_provider = (
        None
        if args.no_roi_reclassify
        else RoiConfigProvider(args.api, args.roi_refresh_seconds)
    )
    cycle_index = 0
    try:
        while True:
            if cycle_index > 0:
                for tracker in position_trackers.values():
                    tracker.reset_active()
            store_seq = {}  # 매장별 프레임 인덱스(한 바퀴마다 초기화)
            cycle_sent = 0
            for tick_index, batch in enumerate(state_batches):
                current = datetime.now(timezone.utc)
                for state in batch:
                    cycle_sent += 1
                    sid = state["store_id"]
                    camera_id = state.get("camera_id", f"{sid}-cam1")
                    idx = store_seq.get(sid, 0)
                    if args.frames_dir or args.raw_frames_dir:
                        store_seq[sid] = idx + 1
                    runtime_state = state
                    if roi_provider is not None:
                        roi_config = roi_provider.get(sid, camera_id)
                        if roi_config is not None:
                            runtime_state = reclassify_state_for_roi(
                                state,
                                roi_config,
                                processed_at=current,
                            )
                    outgoing = prepare_state(
                        runtime_state,
                        preserve_timestamp=args.preserve_timestamps,
                        captured_at=current,
                    )
                    occupancy = prepare_occupancy(
                        runtime_state,
                        preserve_timestamp=args.preserve_timestamps,
                        captured_at=current,
                        position_tracker=position_trackers[sid],
                        id_prefix=f"cycle-{cycle_index}" if args.loop else None,
                    )
                    metadata = snapshot_metadata(outgoing)
                    # 상태별 분석 이미지를 API로 업로드(이미지·숫자 동기)
                    # 이미지는 매장별 폴더: <frames-dir>/<store_id>/{k:04d}.jpg
                    # 승인 ROI를 런타임에 다시 적용할 때 과거 ROI가 그려진 분석본은
                    # 새 메타데이터로 업로드하지 않는다. 대시보드는 원본 위에 현재
                    # ROI와 재판정 좌표를 겹쳐 분석 화면을 만든다.
                    if args.frames_dir and roi_provider is None:
                        src = args.frames_dir / sid / f"{idx:04d}.jpg"
                        if src.exists():
                            try:
                                post_snapshot(
                                    args.api,
                                    sid,
                                    src.read_bytes(),
                                    metadata=metadata,
                                )
                            except urllib.error.URLError as exc:
                                print(
                                    f"  [{cycle_sent}] 이미지 업로드 실패: "
                                    f"{exc.reason}"
                                )
                    if args.raw_frames_dir:
                        raw_src = args.raw_frames_dir / sid / f"{idx:04d}.jpg"
                        if raw_src.exists():
                            try:
                                post_snapshot(
                                    args.api,
                                    sid,
                                    raw_src.read_bytes(),
                                    raw=True,
                                    metadata=metadata,
                                )
                            except urllib.error.URLError as exc:
                                print(
                                    f"  [{cycle_sent}] 원본 이미지 업로드 실패: "
                                    f"{exc.reason}"
                                )
                    try:
                        post_state(state_url, outgoing)
                        state_sent += 1
                    except urllib.error.URLError as exc:
                        failed += 1
                        print(
                            f"  [{cycle_sent}] 상태 전송 실패: {exc.reason} "
                            "(API가 떠 있는지 확인)"
                        )

                    occupancy_url = (
                        args.api.rstrip("/")
                        + f"/internal/stores/{sid}/occupancy"
                    )
                    try:
                        post_state(occupancy_url, occupancy)
                        occupancy_sent += 1
                    except urllib.error.URLError as exc:
                        failed += 1
                        print(f"  [{cycle_sent}] 위치 전송 실패: {exc.reason}")

                    if cycle_sent % 10 == 0 or cycle_sent == len(states):
                        print(
                            f"  [{cycle_sent}/{len(states)}] "
                            f"인원 {outgoing['visible_person_count']} / "
                            f"대기 {outgoing['queue_count_estimate']} / "
                            f"위치 {len(occupancy['agents'])}"
                        )

                is_last_tick = tick_index == len(state_batches) - 1
                if not is_last_tick or args.loop:
                    delay = args.interval
                    if args.realtime:
                        nxt = tick_index + 1
                        # 다음 시점과의 실제 captured_at 간격만큼 대기(배속 반영).
                        # 루프 경계(다음 없음/시각 역전)에서는 기본 간격으로 대체.
                        if (
                            nxt < len(tick_times)
                            and tick_times[tick_index] is not None
                            and tick_times[nxt] is not None
                        ):
                            gap = (
                                tick_times[nxt] - tick_times[tick_index]
                            ).total_seconds()
                            if gap > 0:
                                delay = gap / max(args.speed, 0.01)
                    time.sleep(delay)
            if not args.loop:
                break
            cycle_index += 1
            print("--- 처음부터 다시 재생 ---")
    except KeyboardInterrupt:
        print("\n중단됨")

    print(
        f"\n전송 완료 상태 {state_sent}건 / "
        f"위치 {occupancy_sent}건 / 실패 {failed}건"
    )


if __name__ == "__main__":
    main()
