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
    load_zones, foot_point, assign_zone, build_store_state, ZONE_COLOR, KST,
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

# 스냅샷/이미지 출력 경로 (--snapshot 데모 프레임, --live/배치 이미지)
SNAP_SEG = {"store-001": "28", "store-002": "8"}  # --snapshot 데모 세그(활동 보이는)
SNAP_DIR = Path(__file__).resolve().parent / "outputs" / "snapshots"
FRAMES_DIR = SNAP_DIR / "frames"  # 상태별 분석 이미지({i:04d}.jpg, states 배열과 같은 순서)

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
    """자세 판정. 상체-허벅지 각도(어깨-엉덩이-무릎)를 주 신호로 사용.

    상체는 탑다운 CCTV에서도 잘 보이고, 앉으면 굽고(~90°) 서면 펴진다(~180°).
    무릎 각도(엉덩이-무릎-발목)는 발목이 자주 가려 보조로만. 정보 없으면 unknown.
    (구버전은 무릎 각도의 max만 봐서 다리 가리면 unknown 다발 + 한 다리만 펴져도 오판.)
    """
    torso = []
    for sh, hip, kn in [(5, 11, 13), (6, 12, 14)]:
        if cf[sh] > 0.3 and cf[hip] > 0.3 and cf[kn] > 0.3:
            torso.append(_angle(kp[sh], kp[hip], kp[kn]))
    knee = []
    for hip, kn, an in [(11, 13, 15), (12, 14, 16)]:
        if cf[hip] > 0.3 and cf[kn] > 0.3 and cf[an] > 0.3:
            knee.append(_angle(kp[hip], kp[kn], kp[an]))
    if torso:
        t = max(torso)                       # 더 펴진 쪽
        if t < 135:
            return "sit"                     # 상체-허벅지 굽음 → 앉음
        if t >= 160 and (not knee or max(knee) >= 150):
            return "stand"                   # 상체 폄 + (무릎도 폄 또는 무릎 안 보임)
        return "sit"                         # 애매하면 보수적으로 앉음
    if knee:
        return "stand" if max(knee) >= 160 else "sit"
    return "unknown"


def dwell_waiting(pose_model, wait_zone, frames):
    """세그먼트 하나 → 현재(마지막 프레임) 대기 인원.

    대기 = **마지막 프레임에 대기 구역 안에서 서있고**, 구간 내 '서있음' 누적 N프레임 이상
           AND 서있음 > 앉음. (지나가는 사람·앉은 손님·이미 나가서 앉은 사람 제외)
    누적만 보면 '한때 대기했다 나간 사람'까지 세므로, 마지막 프레임 존재를 함께 본다.
    """
    st, si = collections.Counter(), collections.Counter()
    cur = set()  # 마지막으로 처리한 프레임의 '구역 안 서있음' 트랙
    for i, path in enumerate(frames):
        r = pose_model.track(read(path), persist=(i > 0), conf=0.30, iou=0.5,
                             tracker="bytetrack.yaml", verbose=False)[0]
        cur = set()
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
                cur.add(tid)
            elif pos == "sit":
                si[tid] += 1
    return sum(1 for t in cur if st[t] >= N_DWELL and st[t] > si.get(t, 0))


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


def run(limit=None, gen_images=True):
    """세그먼트 교차 순서로 상태 + (선택)분석 이미지를 함께 생성.

    상태와 이미지를 같은 `analyze_and_render`로 만들어 항상 일치. 이미지는
    FRAMES_DIR/{i:04d}.jpg 로 states 배열과 같은 순서(인덱스) 저장 → replay가
    전송 인덱스에 맞춰 현재 이미지로 교체하면 대시보드에서 이미지·숫자가 동기.
    반환: states(교차 배치된 리스트).
    """
    ft = YOLO(CAFE_MODEL) if Path(CAFE_MODEL).exists() else YOLO("yolo11s.pt")
    pose = YOLO(POSE_MODEL)
    base = datetime.now(KST)
    seg_map = {s["store_id"]: seg_dirs(s["clip"]) for s in STORES}
    n = min(len(v) for v in seg_map.values())
    if limit:
        n = min(n, limit)
    if gen_images:
        FRAMES_DIR.mkdir(parents=True, exist_ok=True)

    states = []
    store_k = {s["store_id"]: 0 for s in STORES}  # 매장별 프레임 인덱스
    for t in range(n):
        for store in STORES:
            seg = seg_map[store["store_id"]][t]
            if not seg_frames(store["clip"], seg):
                continue
            img, c = analyze_and_render(ft, pose, store, seg)
            ts = base + timedelta(seconds=INTERVAL * t)
            state = build_store_state(
                {"staff": c["staff"], "waiting": c["waiting"]}, c["customers"],
                c["waiting"], camera_id=f"{store['store_id']}-cam1",
                store_id=store["store_id"], quality=c["quality"], captured_at=ts)
            state["model_version"] = MODEL_VERSION
            state["positions"] = c["positions"]  # 디지털 트윈용(POST 시 replay가 제거)
            states.append(state)
            if gen_images:
                # 매장별 폴더에 매장별 인덱스로 저장: frames/<store_id>/{k:04d}.jpg
                sdir = FRAMES_DIR / store["store_id"]
                sdir.mkdir(parents=True, exist_ok=True)
                k = store_k[store["store_id"]]
                cv2.imencode(".jpg", img)[1].tofile(str(sdir / f"{k:04d}.jpg"))
            store_k[store["store_id"]] += 1
        if t % 10 == 0 or t == n - 1:
            print(f"  세그 {t + 1}/{n} (states {len(states)}"
                  f"{', 이미지 저장' if gen_images else ''})")
    return states


def _header(img, text):
    cv2.putText(img, text, (14, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 6)
    cv2.putText(img, text, (14, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)


def save_snapshot(store_id, img):
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SNAP_DIR / f"{store_id}.jpg"
    cv2.imencode(".jpg", img)[1].tofile(str(out_path))
    return out_path


def upload_snapshot(api, store_id, img):
    """분석 이미지를 백엔드에 업로드(백엔드 #85 계약).

    POST /internal/stores/{store_id}/vision-snapshot (multipart form field 'image').
    대시보드는 GET /api/stores/{store_id}/vision/latest 로 조회.
    """
    import urllib.request
    jpg = cv2.imencode(".jpg", img)[1].tobytes()
    boundary = "----visionsnapshotboundary"
    body = (f"--{boundary}\r\n".encode()
            + b'Content-Disposition: form-data; name="image"; filename="snapshot.jpg"\r\n'
            + b"Content-Type: image/jpeg\r\n\r\n" + jpg
            + f"\r\n--{boundary}--\r\n".encode())
    url = api.rstrip("/") + f"/internal/stores/{store_id}/vision-snapshot"
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    urllib.request.urlopen(req, timeout=10).close()


def waiter_feet(pose_model, zones, frames):
    """세그먼트를 pose로 추적 → 마지막 프레임의 '대기 확정' 사람 발 위치 목록 + 마지막 프레임 경로.

    대기 = 마지막 프레임에 대기 구역 안 서있음 AND 누적 서있음 N프레임 이상 AND 서있음>앉음.
    (dwell_waiting과 동일 기준. 이미지에서 이 사람들만 대기로 칠하려고 발 위치를 반환.)
    """
    wait_zone = [z for z in zones if z["key"] == "waiting"]
    st, si = collections.Counter(), collections.Counter()
    cur_foot = {}   # 마지막 프레임의 tid -> 발 위치(구역 안 서있음)
    last_path = frames[-1] if frames else None
    for i, path in enumerate(frames):
        r = pose_model.track(read(path), persist=(i > 0), conf=0.30, iou=0.5,
                             tracker="bytetrack.yaml", verbose=False)[0]
        cur_foot = {}
        last_path = path
        if r.boxes.id is None:
            continue
        ids = r.boxes.id.cpu().numpy().astype(int)
        boxes = r.boxes.xyxy.cpu().numpy()
        kps = r.keypoints.xy.cpu().numpy()
        cfs = r.keypoints.conf.cpu().numpy() if r.keypoints.conf is not None else None
        for j, tid in enumerate(ids):
            foot = foot_point(boxes[j])
            if assign_zone(foot, wait_zone) is None:
                continue
            pos = posture(kps[j], cfs[j]) if cfs is not None else "unknown"
            if pos == "stand":
                st[tid] += 1
                cur_foot[tid] = foot
            elif pos == "sit":
                si[tid] += 1
    feet = [cur_foot[t] for t in cur_foot
            if st[t] >= N_DWELL and st[t] > si.get(t, 0)]
    return last_path, feet


def render_analysis(img, zones, ft_boxes, wfeet):
    """FT 탐지 박스 + 직원/대기 ROI를 그린다. 발점 색은 dwell 기준으로 통일:
       직원구역=보라, (대기자 발 위치 근처)=주황, 그 외=파랑(좌석/기타).
       → 앉은 사람은 대기 구역 안이라도 주황이 아님.
    반환: {total, staff, waiting, customers}.
    """
    ov = img.copy()
    for z in zones:
        cv2.fillPoly(ov, [z["polygon"]], ZONE_COLOR.get(z["key"], (150, 150, 150)))
    cv2.addWeighted(ov, 0.3, img, 0.7, 0, img)
    for z in zones:
        cv2.polylines(img, [z["polygon"]], True, ZONE_COLOR.get(z["key"], (150, 150, 150)), 2)

    staff = waiting = 0
    for b in ft_boxes:
        foot = foot_point(b)
        z = assign_zone(foot, zones)
        zk = z["key"] if z else None
        near_waiter = any((foot[0] - wx) ** 2 + (foot[1] - wy) ** 2 < 70 ** 2
                          for wx, wy in wfeet)
        if zk == "staff":
            col = ZONE_COLOR["staff"]
            staff += 1
        elif near_waiter:
            col = ZONE_COLOR["waiting"]
            waiting += 1
        else:
            col = ZONE_COLOR["seating"]
        cv2.rectangle(img, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])), (0, 255, 0), 1)
        cv2.circle(img, foot, 7, col, -1)
        cv2.circle(img, foot, 7, (0, 0, 0), 1)
    total = len(ft_boxes)
    return {"total": total, "staff": staff, "waiting": waiting,
            "customers": max(total - staff, 0)}


def person_positions(ft_boxes, zones):
    """FT 탐지 → 사람별 좌표(이미지 픽셀 1920×1080) + 구역 + 유형. 디지털 트윈용.

    각 사람: {x, y(발 위치), zone: waiting/staff/seating, type: staff/customer}.
    """
    out = []
    for b in ft_boxes:
        fx, fy = foot_point(b)
        z = assign_zone((int(fx), int(fy)), zones)
        zk = z["key"] if z else None
        out.append({
            "x": int(fx), "y": int(fy),
            "zone": zk if zk in ("waiting", "staff") else "seating",
            "type": "staff" if zk == "staff" else "customer",
        })
    return out


def analyze_and_render(ft_model, pose_model, store, seg):
    """매장 한 세그먼트 → (마지막프레임 주석 이미지, 집계). 이미지·상태 공통 경로.

    - 인원/직원: 파인튜닝 모델(정확). - 대기: pose+dwell(서있는 대기자만).
    - 대기자만 주황으로 칠해 앉은 사람 오표시 없음. 헤더=집계와 일치.
    - c["positions"]: 사람별 좌표(디지털 트윈용, 이미지 픽셀).
    """
    _, zones = load_zones(ZONES_DIR / f"{store['store_id']}_zones.json")
    frames = seg_frames(store["clip"], seg)
    if not frames:
        raise SystemExit(f"{store['store_id']} 세그 {seg} 프레임 없음")
    last_path, wfeet = waiter_feet(pose_model, zones, frames)
    img = read(last_path)
    quality = frame_quality(img)
    res = ft_model.predict(img, classes=[0], conf=0.30, iou=0.5,
                           agnostic_nms=True, verbose=False)[0]
    ft_boxes = res.boxes.xyxy.cpu().numpy()
    c = render_analysis(img, zones, ft_boxes, wfeet)
    _header(img, f"{store['store_id']}  customer {c['customers']}  "
                 f"wait {c['waiting']}  staff {c['staff']}  [{quality}]")
    c["quality"] = quality
    c["positions"] = person_positions(ft_boxes, zones)
    return img, c


def run_snapshot(seg_override=None):
    ft = YOLO(CAFE_MODEL) if Path(CAFE_MODEL).exists() else YOLO("yolo11s.pt")
    pose = YOLO(POSE_MODEL)
    print(f"=== 분석 스냅샷 생성 → {SNAP_DIR} ===")
    for store in STORES:
        seg = seg_override or SNAP_SEG.get(store["store_id"], "0")
        img, c = analyze_and_render(ft, pose, store, seg)
        p = save_snapshot(store["store_id"], img)
        print(f"  {store['store_id']} (seg {seg}): 손님 {c['customers']} "
              f"대기 {c['waiting']} 직원 {c['staff']} [{c['quality']}] → {p.name}")


def run_live(api, interval, limit=None):
    """(ㄴ) 이미지↔상태 동기 재생. 세그먼트마다 분석 이미지 + StoreState를 함께 생성.

    같은 세그먼트에서 이미지(탐지+ROI, 대기자만 주황)와 상태(인원/대기/직원)를 만들어
    outputs/snapshots/<store>.jpg 갱신 + API로 POST → 이미지와 숫자가 항상 일치.
    모델·GPU·데이터가 있는 머신에서 실행하고, 백엔드가 SNAP_DIR을 서빙한다.

    실행: py cafe_stores.py --live --post http://localhost:8000 --interval 3
    """
    import time
    import urllib.request

    ft = YOLO(CAFE_MODEL) if Path(CAFE_MODEL).exists() else YOLO("yolo11s.pt")
    pose = YOLO(POSE_MODEL)
    seg_map = {s["store_id"]: seg_dirs(s["clip"]) for s in STORES}
    n = min(len(v) for v in seg_map.values())
    if limit:
        n = min(n, limit)
    url = api.rstrip("/") + "/internal/store-states"
    print(f"=== LIVE 동기 재생: {n}세그 × {len(STORES)}매장 → {url} (간격 {interval}s) ===")
    print("이미지 갱신: " + str(SNAP_DIR) + "\n중단 Ctrl+C\n")

    try:
        for t in range(n):
            for store in STORES:
                seg = seg_map[store["store_id"]][t]
                if not seg_frames(store["clip"], seg):
                    continue
                img, c = analyze_and_render(ft, pose, store, seg)
                save_snapshot(store["store_id"], img)   # 로컬 디버그용
                try:                                     # 이미지 API 업로드(#85)
                    upload_snapshot(api, store["store_id"], img)
                except Exception as exc:  # noqa: BLE001
                    print(f"  이미지 업로드 실패({store['store_id']}): {exc}")
                state = build_store_state(
                    {"staff": c["staff"], "waiting": c["waiting"]}, c["customers"],
                    c["waiting"], camera_id=f"{store['store_id']}-cam1",
                    store_id=store["store_id"], quality=c["quality"],
                    captured_at=datetime.now(KST))
                state["model_version"] = MODEL_VERSION
                req = urllib.request.Request(
                    url, data=json.dumps(state).encode("utf-8"),
                    headers={"Content-Type": "application/json"}, method="POST")
                try:
                    urllib.request.urlopen(req, timeout=5).close()
                except Exception as exc:  # noqa: BLE001
                    print(f"  POST 실패({store['store_id']}): {exc}")
            if t % 10 == 0:
                print(f"  세그 {t + 1}/{n} 상태+이미지 갱신")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n중단됨")


def main():
    ap = argparse.ArgumentParser(description="CAFE 다매장 인원·대기·직원 집계(dwell)")
    ap.add_argument("--limit", type=int, default=None, help="매장별 앞 N세그만(빠른 확인)")
    ap.add_argument("--post", default=None, help="API 베이스 URL로 전송(예: http://localhost:8000)")
    ap.add_argument("--snapshot", action="store_true",
                    help="매장별 분석 이미지(탐지+ROI)를 outputs/snapshots/에 1장 생성")
    ap.add_argument("--snapshot-seg", default=None, help="스냅샷에 쓸 세그먼트 번호(전 매장 공통)")
    ap.add_argument("--live", action="store_true",
                    help="이미지↔상태 동기 재생: 세그먼트마다 이미지 갱신 + StoreState POST")
    ap.add_argument("--interval", type=float, default=3.0, help="--live 세그먼트 간격(초)")
    ap.add_argument("--no-images", action="store_true",
                    help="상태만 생성하고 분석 이미지(frames/)는 저장하지 않음")
    args = ap.parse_args()

    if args.snapshot:
        run_snapshot(args.snapshot_seg)
        return

    if args.live:
        if not args.post:
            raise SystemExit("--live 에는 --post <API URL> 이 필요합니다 (예: --post http://localhost:8000)")
        run_live(args.post, args.interval, args.limit)
        return

    states = run(args.limit, gen_images=not args.no_images)

    out = Path(__file__).resolve().parents[2] / "samples" / "cafe_stores_states.json"
    out.parent.mkdir(exist_ok=True)
    doc = {
        "note": ("CAFE 다매장(현재 store-001·002) 집계. 인원=파인튜닝 탐지-직원, "
                 "대기=대기구역+서있음+체류(ByteTrack), 직원=직원구역. "
                 "captured_at은 합성 시각(실측 아님). states 순서=분석 이미지 "
                 "outputs/snapshots/frames/{i:04d}.jpg 순서."),
        "stores": [{"store_id": s["store_id"], "name": s["name"], "clip": s["clip"]}
                   for s in STORES],
        "count": len(states),
        "states": states,
    }
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n완료: {len(states)}건 → {out}")
    for s in STORES:
        ss = [x for x in states if x["store_id"] == s["store_id"]]
        if not ss:
            continue
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
            payload = {k: v for k, v in s.items() if k != "positions"}
            req = urllib.request.Request(
                url, data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    ok += resp.status < 300
            except Exception as exc:  # noqa: BLE001
                print(f"  POST 실패({s['store_id']}): {exc}")
        print(f"POST {url} → 성공 {ok}/{len(states)}")


if __name__ == "__main__":
    main()
