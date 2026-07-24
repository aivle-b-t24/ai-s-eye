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
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FILE = REPO_ROOT / "samples" / "cafe_stores_states.json"


def load_states(path: Path) -> list[dict]:
    """결과 파일 → store_state 목록. 배열/객체 두 형식 모두 지원."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "states" in data:
        # {"states": [{"frame": n, "state": {...}}, ...]} 형식
        return [s["state"] if "state" in s else s for s in data["states"]]
    if isinstance(data, list):
        return [s["state"] if isinstance(s, dict) and "state" in s else s for s in data]
    return [data]  # 단건


def post_state(url: str, state: dict, timeout: float = 5.0) -> int:
    body = json.dumps(state).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
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
    if not preserve_timestamp:
        current = captured_at or datetime.now(timezone.utc)
        outgoing["captured_at"] = current.isoformat()
    return outgoing


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
    args = ap.parse_args()

    if not args.file.exists():
        raise SystemExit(f"결과 파일이 없습니다: {args.file}")

    states = load_states(args.file)
    if args.limit:
        states = states[: args.limit]
    url = args.api.rstrip("/") + "/internal/store-states"

    print(f"재생 시작: {len(states)}건 / 간격 {args.interval}초 → {url}")
    print("중단하려면 Ctrl+C\n")

    sent = failed = 0
    try:
        while True:
            for i, state in enumerate(states, 1):
                outgoing = prepare_state(
                    state,
                    preserve_timestamp=args.preserve_timestamps,
                )
                try:
                    post_state(url, outgoing)
                    sent += 1
                except urllib.error.URLError as exc:
                    failed += 1
                    print(f"  [{i}] 전송 실패: {exc.reason} (API가 떠 있는지 확인)")
                else:
                    if i % 10 == 0 or i == len(states):
                        print(f"  [{i}/{len(states)}] "
                              f"인원 {outgoing['visible_person_count']} / "
                              f"대기 {outgoing['queue_count_estimate']}")
                time.sleep(args.interval)
            if not args.loop:
                break
            print("--- 처음부터 다시 재생 ---")
    except KeyboardInterrupt:
        print("\n중단됨")

    print(f"\n전송 완료 {sent}건 / 실패 {failed}건")


if __name__ == "__main__":
    main()
