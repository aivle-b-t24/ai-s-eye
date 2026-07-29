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
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FILE = REPO_ROOT / "samples" / "cafe_stores_states.json"
DEFAULT_FRAME_WIDTH = 1920
DEFAULT_FRAME_HEIGHT = 1080


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
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
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
) -> int:
    """분석본 또는 ROI 설정용 원본 이미지를 API에 업로드한다."""
    boundary = "----visionsnapshotboundary"
    body = (
        f"--{boundary}\r\n".encode()
        + b'Content-Disposition: form-data; name="image"; filename="snapshot.jpg"\r\n'
        + b"Content-Type: image/jpeg\r\n\r\n"
        + image_bytes
        + f"\r\n--{boundary}--\r\n".encode()
    )
    endpoint = "vision-raw" if raw else "vision-snapshot"
    url = api.rstrip("/") + f"/internal/stores/{store_id}/{endpoint}"
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status


def prepare_state(
    state: dict,
    *,
    preserve_timestamp: bool = False,
    captured_at: datetime | None = None,
) -> dict:
    """전송할 상태를 복사하고, 실시간 재생이면 측정 시각을 현재로 바꾼다.

    PostgreSQL은 captured_at이 가장 최근인 상태를 조회한다. 저장된 합성 시각을
    그대로 반복 전송하면 한 바퀴 뒤의 데이터가 최신 상태가 되지 못하므로,
    재생할 때는 현재 UTC 시각을 기본으로 사용한다.
    """
    outgoing = state.copy()
    outgoing.pop("positions", None)  # 디지털 트윈용 필드 → API 스키마에 없으므로 제거
    if not preserve_timestamp:
        current = captured_at or datetime.now(timezone.utc)
        outgoing["captured_at"] = current.isoformat()
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
    if preserve_timestamp:
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

        agents.append(
            {
                "id": agent_id,
                "x": position_x,
                "y": position_y,
                "role": role,
                "state": agent_state,
                "zone": zone,
            }
        )

    store_id = state["store_id"]
    return {
        "schema_version": "1.0",
        "store_id": store_id,
        "camera_id": state.get("camera_id", f"{store_id}-cam1"),
        "mode": "live",
        "captured_at": timestamp,
        "coordinate_space": "normalized_image",
        "agents": agents,
    }


def main():
    ap = argparse.ArgumentParser(description="분석 결과를 API로 재생 전송")
    ap.add_argument("--file", type=Path, default=DEFAULT_FILE, help="결과 JSON 경로")
    ap.add_argument("--api", default="http://localhost:8000", help="API 베이스 URL")
    ap.add_argument("--interval", type=float, default=2.0, help="전송 간격(초)")
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
    args = ap.parse_args()

    if not args.file.exists():
        raise SystemExit(f"결과 파일이 없습니다: {args.file}")

    states = load_states(args.file)
    if args.limit:
        states = states[: args.limit]
    state_batches = group_states_by_tick(states)
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
                    outgoing = prepare_state(
                        state,
                        preserve_timestamp=args.preserve_timestamps,
                        captured_at=current,
                    )
                    occupancy = prepare_occupancy(
                        state,
                        preserve_timestamp=args.preserve_timestamps,
                        captured_at=current,
                        position_tracker=position_trackers[state["store_id"]],
                        id_prefix=f"cycle-{cycle_index}" if args.loop else None,
                    )
                    # 상태별 분석 이미지를 API로 업로드(이미지·숫자 동기)
                    # 이미지는 매장별 폴더: <frames-dir>/<store_id>/{k:04d}.jpg
                    sid = state["store_id"]
                    idx = store_seq.get(sid, 0)
                    if args.frames_dir or args.raw_frames_dir:
                        store_seq[sid] = idx + 1
                    if args.frames_dir:
                        src = args.frames_dir / sid / f"{idx:04d}.jpg"
                        if src.exists():
                            try:
                                post_snapshot(args.api, sid, src.read_bytes())
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
                        + f"/internal/stores/{state['store_id']}/occupancy"
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
                    time.sleep(args.interval)
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
