"""CAFE 다매장(프랜차이즈) 인원·대기·직원 집계 → 매장별 StoreState 시계열.

현재 프로젝트는 대표 매장 2곳(store-001, store-002)만 운영한다.
매장을 늘리려면 STORES에 항목을 추가하고 zones/<store_id>_zones.json 을 그린 뒤 다시 실행.

집계 방식(최신):
- 인원수(visible_person_count) = 파인튜닝 모델(best.pt) 탐지 - 직원 (= 손님)
- 대기(queue_count_estimate)   = 대기 구역 + 서있음(pose) + N프레임 체류(ByteTrack)
                                  → 그 세그먼트(시간 윈도) 동시 대기 인원
- 직원(zone_counts.staff)      = 직원 구역(카운터 뒤) 탐지 수 → 손님에서 제외

시간축: CAFE는 촬영 시각이 없어 세그먼트 순서를 시간축으로 본다(captured_at은 합성).
출력: samples/cafe_stores_states.json  (replay_states.py 로 재생)

경로는 환경변수로 덮어쓸 수 있다:
  AISEYE_CAFE_ROOT  = CAFE 이미지 루트, AISEYE_CAFE_MODEL = 파인튜닝 가중치 경로

실행:
  py services/vision-worker/cafe_stores.py                 # 전체 클립
  py services/vision-worker/cafe_stores.py --limit 60      # 앞 60세그(빠른 확인)
  py services/vision-worker/cafe_stores.py --post http://localhost:8000
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import os
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from roi_zone_counter import (
    load_zones, foot_point, assign_zone, build_store_state, KST,
)

CAFE_ROOT = Path(os.getenv(
    "AISEYE_CAFE_ROOT", r"D:\Cafe_Dataset\Cafe_Dataset\Dataset\cafe"))
CAFE_MODEL = os.getenv(
    "AISEYE_CAFE_MODEL", r"D:\Cafe_Dataset\yolo_runs\cafe_ft\weights\best.pt")
POSE_MODEL = "yolo11s-pose.pt"   # 자동 다운로드(서있음/앉음 + 추적)
MODEL_VERSION = "yolo11s-cafe-ft+pose-dwell"
ZONES_DIR = Path(__file__).resolve().parent / "zones"
N_DWELL = 8        # 대기 구역 안 '서있음' 이 프레임 수 이상이면 대기
INTERVAL = 0.5     # 합성 시각 간격(초)

# 운영 매장. 늘리려면 여기에 추가 + zones/<store_id>_zones.json 작성.
STORES = [
    {"store_id": "store-001", "name": "1호점(CAFE 7g1)", "clip": "5"},
    {"store_id": "store-002", "name": "2호점",          "clip": "21"},
]


def read(path):
    return cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)


def seg_dirs(clip):
    return sorted([d.name for d in (CAFE_ROOT / clip).iterdir()
                   if d.is_dir() and d.name.isdigit()], key=int)


def seg_frames(clip, seg):
    return sorted((CAFE_ROOT / clip / seg / "images").glob("*.jpg"),
                  key=lambda p: int("".join(filter(str.isdigit, p.stem)) or 0))


def _angle(a, b, c):
    v1, v2 = a - b, c - b
    cos = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6)
    return math.degrees(math.acos(max(-1, min(1, cos))))


def posture(kp, cf):
    """무릎 각도로 서있음/앉음 판정. 다리 안 보이면 unknown."""
    best = None
    for hip, knee, ank in [(11, 13, 15), (12, 14, 16)]:
        if cf[hip] > 0.3 and cf[knee] > 0.3 and cf[ank] > 0.3:
            a = _angle(kp[hip], kp[knee], kp[ank])
            best = a if best is None else max(best, a)
    if best is None:
        return "unknown"
    return "stand" if best >= 150 else "sit"


def dwell_waiting(pose_model, wait_zone, frames):
    """세그먼트 하나 → 동시 대기 인원.

    대기 구역 안에서 '서있음' N프레임 이상 AND 서있음 > 앉음(다수결)인 트랙 = 대기.
    (앉은 손님·지나가는 사람 제외)
    """
    st, si = collections.Counter(), collections.Counter()
    for i, path in enumerate(frames):
        r = pose_model.track(read(path), persist=(i > 0), conf=0.30, iou=0.5,
                             tracker="bytetrack.yaml", verbose=False)[0]
        if r.boxes.id is None:
            continue
        ids = r.boxes.id.cpu().numpy().astype(int)
        boxes = r.boxes.xyxy.cpu().numpy()
        kps = r.keypoints.xy.cpu().numpy()
        cfs = r.keypoints.conf.cpu().numpy() if r.keypoints.conf is not None else None
        for j, tid in enumerate(ids):
            if assign_zone(foot_point(boxes[j]), wait_zone) is None:
                continue
            pos = posture(kps[j], cfs[j]) if cfs is not None else "unknown"
            if pos == "stand":
                st[tid] += 1
            elif pos == "sit":
                si[tid] += 1
    return sum(1 for t in st if st[t] >= N_DWELL and st[t] > si.get(t, 0))


def frame_quality(img):
    """프레임 유효성 → quality_status. 사람 수와 무관(0명은 정상 빈 매장).

    - 디코드 실패(None) 또는 거의 검은 화면(카메라 꺼짐/가림) = 영상 이상 → "low"
    - 그 외 정상 프레임 → "normal"  (사람이 0명이어도 정상)
    """
    if img is None:
        return "low"
    return "low" if float(img.mean()) < 8 else "normal"


def head_and_staff(ft_model, staff_zone, frame_path):
    """대표 프레임에서 파인튜닝 모델로 총원 + 직원 수 + 프레임 품질."""
    img = read(frame_path)
    quality = frame_quality(img)
    if img is None:
        return 0, 0, quality
    r = ft_model.predict(img, classes=[0], conf=0.30, iou=0.5,
                         agnostic_nms=True, verbose=False)[0]
    boxes = r.boxes.xyxy.cpu().numpy()
    staff = sum(1 for b in boxes if assign_zone(foot_point(b), staff_zone) is not None)
    return len(boxes), staff, quality


def run(limit=None):
    ft = YOLO(CAFE_MODEL) if Path(CAFE_MODEL).exists() else YOLO("yolo11s.pt")
    pose = YOLO(POSE_MODEL)
    base = datetime.now(KST)

    per_store = {}
    for store in STORES:
        _, zones = load_zones(ZONES_DIR / f"{store['store_id']}_zones.json")
        wait_zone = [z for z in zones if z["key"] == "waiting"]
        staff_zone = [z for z in zones if z["key"] == "staff"]
        segs = seg_dirs(store["clip"])
        if limit:
            segs = segs[:limit]
        print(f"{store['store_id']}: {len(segs)}세그먼트 처리")
        states = []
        for k, seg in enumerate(segs):
            frames = seg_frames(store["clip"], seg)
            if not frames:
                continue
            waiting = dwell_waiting(pose, wait_zone, frames)
            total, staff, quality = head_and_staff(
                ft, staff_zone, frames[len(frames) // 2])
            customers = max(total - staff, 0)
            ts = base + timedelta(seconds=INTERVAL * k)
            state = build_store_state(
                {"staff": staff, "waiting": waiting}, customers, waiting,
                camera_id=f"{store['store_id']}-cam1", store_id=store["store_id"],
                quality=quality, captured_at=ts,
            )
            state["model_version"] = MODEL_VERSION
            states.append(state)
            if k % 50 == 0:
                print(f"  {store['store_id']} {k}/{len(segs)} "
                      f"(손님 {customers} 대기 {waiting} 직원 {staff})")
        per_store[store["store_id"]] = states
    return per_store


def interleave(per_store):
    """세그먼트 순서로 매장을 교차 배치(대시보드가 매장별로 갱신되게)."""
    lists = [per_store[s["store_id"]] for s in STORES]
    out = []
    for i in range(max(len(x) for x in lists)):
        for lst in lists:
            if i < len(lst):
                out.append(lst[i])
    return out


def main():
    ap = argparse.ArgumentParser(description="CAFE 다매장 인원·대기·직원 집계(dwell)")
    ap.add_argument("--limit", type=int, default=None, help="매장별 앞 N세그만(빠른 확인)")
    ap.add_argument("--post", default=None, help="API 베이스 URL로 전송(예: http://localhost:8000)")
    args = ap.parse_args()

    per_store = run(args.limit)
    states = interleave(per_store)

    out = Path(__file__).resolve().parents[2] / "samples" / "cafe_stores_states.json"
    out.parent.mkdir(exist_ok=True)
    doc = {
        "note": ("CAFE 다매장(현재 store-001·002) 집계. 인원=파인튜닝 탐지-직원, "
                 "대기=대기구역+서있음+체류(ByteTrack), 직원=직원구역. "
                 "captured_at은 합성 시각(실측 아님)."),
        "stores": [{"store_id": s["store_id"], "name": s["name"], "clip": s["clip"]}
                   for s in STORES],
        "count": len(states),
        "states": states,
    }
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n완료: {len(states)}건 → {out}")
    for s in STORES:
        ss = per_store[s["store_id"]]
        q = [x["queue_count_estimate"] for x in ss]
        c = [x["visible_person_count"] for x in ss]
        st = [x["zone_counts"]["staff"] for x in ss]
        print(f"  {s['store_id']}: 손님 평균 {sum(c)/len(c):.1f} / "
              f"대기 평균 {sum(q)/len(q):.2f} 최대 {max(q)} / 직원 평균 {sum(st)/len(st):.2f}")

    if args.post:
        import urllib.request
        url = args.post.rstrip("/") + "/internal/store-states"
        ok = 0
        for s in states:
            req = urllib.request.Request(
                url, data=json.dumps(s).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    ok += resp.status < 300
            except Exception as exc:  # noqa: BLE001
                print(f"  POST 실패({s['store_id']}): {exc}")
        print(f"POST {url} → 성공 {ok}/{len(states)}")


if __name__ == "__main__":
    main()
