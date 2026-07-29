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
import time
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from roi_zone_counter import (
    parse_zones, foot_point, assign_zone, build_store_state, ZONE_COLOR, KST,
)
from roi_config_client import load_roi_zone_data
from replay_states import post_state, prepare_occupancy

CAFE_ROOT = Path(os.getenv(
    "AISEYE_CAFE_ROOT", r"D:\Cafe_Dataset\Cafe_Dataset\Dataset\cafe"))
CAFE_MODEL = os.getenv(
    "AISEYE_CAFE_MODEL", r"D:\Cafe_Dataset\yolo_runs\cafe_ft\weights\best.pt")
POSE_MODEL = "yolo11s-pose.pt"   # 자동 다운로드(서있음/앉음 + 추적)
TRACKER_CONFIG = os.getenv("AISEYE_TRACKER", "bytetrack.yaml")
MODEL_VERSION = "yolo11s-cafe-ft+pose-dwell"
BASE_MODEL_VERSION = "yolo11s-base+pose-dwell"
ZONES_DIR = Path(__file__).resolve().parent / "zones"
ROI_CACHE_DIR = Path(
    os.getenv(
        "AISEYE_ROI_CACHE_DIR",
        str(Path(__file__).resolve().parent / "outputs" / "roi-cache"),
    )
)
ROI_API_BASE_URL = os.getenv("AISEYE_API_BASE_URL")
ROI_REFRESH_SECONDS = max(
    float(os.getenv("AISEYE_ROI_REFRESH_SECONDS", "2")),
    0.0,
)
ROI_AUTO_REFRESH = False
_ZONE_CACHE: dict[tuple[str, str, int, int], dict] = {}
N_DWELL = 8        # 대기 구역 안 '서있음' 이 프레임 수 이상이면 대기
N_SEATED = 3       # 좌석 구역 안 '앉음' 이 프레임 수 이상이면 착석
# 직원 = 직원구역 누적 체류 상위 K명(track_id 기준). 매장별 직원 수를 설정해 상한.
STAFF_COUNT = {"store-001": 1, "store-002": 1}
INTERVAL = 0.5     # 합성 시각 간격(초)

# 스냅샷/이미지 출력 경로 (--snapshot 데모 프레임, --live/배치 이미지)
SNAP_SEG = {"store-001": "28", "store-002": "8"}  # --snapshot 데모 세그(활동 보이는)
SNAP_DIR = Path(__file__).resolve().parent / "outputs" / "snapshots"
FRAMES_DIR = SNAP_DIR / "frames"  # 상태별 분석 이미지({i:04d}.jpg, states 배열과 같은 순서)
RAW_FRAMES_DIR = SNAP_DIR / "raw-frames"  # ROI 설정용 오버레이 없는 원본

# 운영 매장. 늘리려면 여기에 추가 + zones/<store_id>_zones.json 작성.
STORES = [
    {"store_id": "store-001", "name": "1호점(CAFE 7g1)", "clip": "5"},
    {"store_id": "store-002", "name": "2호점",          "clip": "21"},
]


def read(path):
    return cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)


def load_cafe_model():
    """사람 탐지 모델 한 개를 만든다.

    추적 상태는 YOLO 인스턴스 내부에 유지되므로 카메라별로 별도 인스턴스를
    사용해야 서로 다른 매장의 track_id가 섞이지 않는다.
    """
    return YOLO(CAFE_MODEL) if Path(CAFE_MODEL).exists() else YOLO("yolo11s.pt")


def active_model_version():
    """실제로 불러온 탐지 가중치에 맞는 버전을 반환한다."""
    return MODEL_VERSION if Path(CAFE_MODEL).exists() else BASE_MODEL_VERSION


def load_store_trackers():
    """운영 매장마다 독립된 사람 추적기를 준비한다."""
    if not Path(CAFE_MODEL).exists():
        print(
            f"경고: 파인튜닝 가중치가 없어 일반 yolo11s.pt를 사용합니다: "
            f"{CAFE_MODEL}"
        )
    return {store["store_id"]: load_cafe_model() for store in STORES}


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
    ft_models = load_store_trackers()
    pose = YOLO(POSE_MODEL)
    base = datetime.now(KST)
    seg_map = {s["store_id"]: seg_dirs(s["clip"]) for s in STORES}
    n = min(len(v) for v in seg_map.values())
    if limit:
        n = min(n, limit)
    if gen_images:
        FRAMES_DIR.mkdir(parents=True, exist_ok=True)
        RAW_FRAMES_DIR.mkdir(parents=True, exist_ok=True)

    states = []
    store_k = {s["store_id"]: 0 for s in STORES}  # 매장별 프레임 인덱스
    # 직원 = 직원구역 누적 체류 top-K(STAFF_COUNT). 전체 클립에 걸쳐 누적한다.
    staff_accum = {s["store_id"]: collections.Counter() for s in STORES}
    for t in range(n):
        for store in STORES:
            seg = seg_map[store["store_id"]][t]
            if not seg_frames(store["clip"], seg):
                continue
            img, raw_img, c = analyze_and_render(
                ft_models[store["store_id"]], pose, store, seg,
                staff_accum[store["store_id"]],
            )
            ts = base + timedelta(seconds=INTERVAL * t)
            state = build_store_state(
                {"staff": c["staff"], "waiting": c["waiting"]}, c["customers"],
                c["waiting"], camera_id=f"{store['store_id']}-cam1",
                store_id=store["store_id"], quality=c["quality"], captured_at=ts)
            state["model_version"] = active_model_version()
            state["positions"] = c["positions"]  # 디지털 트윈용(POST 시 replay가 제거)
            states.append(state)
            if gen_images:
                # 매장별 폴더에 매장별 인덱스로 저장: frames/<store_id>/{k:04d}.jpg
                sdir = FRAMES_DIR / store["store_id"]
                raw_dir = RAW_FRAMES_DIR / store["store_id"]
                sdir.mkdir(parents=True, exist_ok=True)
                raw_dir.mkdir(parents=True, exist_ok=True)
                k = store_k[store["store_id"]]
                cv2.imencode(".jpg", img)[1].tofile(str(sdir / f"{k:04d}.jpg"))
                cv2.imencode(".jpg", raw_img)[1].tofile(
                    str(raw_dir / f"{k:04d}.jpg")
                )
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


def upload_snapshot(api, store_id, img, *, raw=False):
    """분석 이미지 또는 ROI 설정용 원본을 백엔드에 업로드한다.

    분석본: POST /internal/stores/{store_id}/vision-snapshot
    원본:   POST /internal/stores/{store_id}/vision-raw
    """
    import urllib.request
    jpg = cv2.imencode(".jpg", img)[1].tobytes()
    boundary = "----visionsnapshotboundary"
    body = (f"--{boundary}\r\n".encode()
            + b'Content-Disposition: form-data; name="image"; filename="snapshot.jpg"\r\n'
            + b"Content-Type: image/jpeg\r\n\r\n" + jpg
            + f"\r\n--{boundary}--\r\n".encode())
    endpoint = "vision-raw" if raw else "vision-snapshot"
    url = api.rstrip("/") + f"/internal/stores/{store_id}/{endpoint}"
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    urllib.request.urlopen(req, timeout=10).close()


def pose_state_feet(pose_model, zones, frames):
    """세그먼트를 pose로 추적해 마지막 프레임의 대기·착석 발 위치를 반환한다.

    대기 = 마지막 프레임에 대기 구역 안 서있음 AND 누적 서있음 N프레임 이상 AND 서있음>앉음.
    착석 = 마지막 프레임에 좌석 구역 안 앉음 AND 누적 앉음 N프레임 이상 AND 앉음>서있음.
    일반 탐지기와 Pose 추적기의 ID 공간이 다르므로 마지막 발 위치로 결과를 연결한다.
    """
    wait_zone = [z for z in zones if z["key"] == "waiting"]
    seating_zone = [z for z in zones if z["key"] == "seating"]
    waiting_stand = collections.Counter()
    waiting_sit = collections.Counter()
    seating_sit = collections.Counter()
    seating_stand = collections.Counter()
    current_waiting = {}
    current_seated = {}
    last_path = frames[-1] if frames else None
    for i, path in enumerate(frames):
        r = pose_model.track(read(path), persist=(i > 0), conf=0.30, iou=0.5,
                             tracker="bytetrack.yaml", verbose=False)[0]
        current_waiting = {}
        current_seated = {}
        last_path = path
        if r.boxes.id is None:
            continue
        ids = r.boxes.id.cpu().numpy().astype(int)
        boxes = r.boxes.xyxy.cpu().numpy()
        kps = r.keypoints.xy.cpu().numpy()
        cfs = r.keypoints.conf.cpu().numpy() if r.keypoints.conf is not None else None
        for j, tid in enumerate(ids):
            foot = foot_point(boxes[j])
            pos = posture(kps[j], cfs[j]) if cfs is not None else "unknown"
            if assign_zone(foot, wait_zone) is not None:
                if pos == "stand":
                    waiting_stand[tid] += 1
                    current_waiting[tid] = foot
                elif pos == "sit":
                    waiting_sit[tid] += 1
            if assign_zone(foot, seating_zone) is not None:
                if pos == "sit":
                    seating_sit[tid] += 1
                    current_seated[tid] = foot
                elif pos == "stand":
                    seating_stand[tid] += 1

    waiting_feet = [
        current_waiting[track_id]
        for track_id in current_waiting
        if (
            waiting_stand[track_id] >= N_DWELL
            and waiting_stand[track_id] > waiting_sit.get(track_id, 0)
        )
    ]
    seated_feet = [
        current_seated[track_id]
        for track_id in current_seated
        if (
            seating_sit[track_id] >= N_SEATED
            and seating_sit[track_id] > seating_stand.get(track_id, 0)
        )
    ]
    return last_path, {"waiting": waiting_feet, "seated": seated_feet}


def render_analysis(img, zones, ft_boxes, pose_feet, track_ids=None, staff_set=None):
    """FT 탐지 박스 + 직원/대기 ROI를 그린다. 발점 색은 dwell 기준으로 통일:
       직원=보라, (대기자 발 위치 근처)=주황, 그 외=파랑(좌석/기타).
       직원 판정: staff_set 주면 그 track_id만 직원(누적 top-K), 없으면 직원구역 소속.
    반환: {total, staff, waiting, customers}.
    """
    ov = img.copy()
    for z in zones:
        cv2.fillPoly(ov, [z["polygon"]], ZONE_COLOR.get(z["key"], (150, 150, 150)))
    cv2.addWeighted(ov, 0.3, img, 0.7, 0, img)
    for z in zones:
        cv2.polylines(img, [z["polygon"]], True, ZONE_COLOR.get(z["key"], (150, 150, 150)), 2)

    staff = waiting = 0
    track_ids = track_ids if track_ids is not None else [None] * len(ft_boxes)
    for b, track_id in zip(ft_boxes, track_ids):
        foot = foot_point(b)
        z = assign_zone(foot, zones)
        zk = z["key"] if z else None
        near_waiter = any((foot[0] - wx) ** 2 + (foot[1] - wy) ** 2 < 70 ** 2
                          for wx, wy in pose_feet["waiting"])
        is_staff = (
            int(track_id) in staff_set
            if staff_set is not None and track_id is not None
            else zk == "staff"
        )
        if is_staff:
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
        if track_id is not None:
            cv2.putText(
                img,
                f"ID {int(track_id)}",
                (int(b[0]), max(int(b[1]) - 6, 16)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (255, 255, 255),
                2,
            )
            cv2.putText(
                img,
                f"ID {int(track_id)}",
                (int(b[0]), max(int(b[1]) - 6, 16)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 0, 0),
                1,
            )
    total = len(ft_boxes)
    return {"total": total, "staff": staff, "waiting": waiting,
            "customers": max(total - staff, 0)}


def person_positions(
    ft_boxes,
    zones,
    pose_feet,
    track_ids=None,
    staff_set=None,
):
    """FT 추적 → 사람별 ID·좌표·구역·유형. 디지털 트윈용.

    각 사람: {track_id, x, y(발 위치), zone, type}.
    직원 판정: staff_set 주면 그 track_id만 직원(누적 top-K), 없으면 직원구역 소속.
    """
    out = []
    track_ids = track_ids if track_ids is not None else [None] * len(ft_boxes)
    if len(track_ids) != len(ft_boxes):
        raise ValueError("track_ids and boxes must have the same length")
    for b, track_id in zip(ft_boxes, track_ids):
        fx, fy = foot_point(b)
        z = assign_zone((int(fx), int(fy)), zones)
        zk = z["key"] if z else None
        is_staff = (
            int(track_id) in staff_set
            if staff_set is not None and track_id is not None
            else zk == "staff"
        )
        is_waiting = any(
            (fx - wx) ** 2 + (fy - wy) ** 2 < 70 ** 2
            for wx, wy in pose_feet["waiting"]
        )
        is_seated = any(
            (fx - sx) ** 2 + (fy - sy) ** 2 < 70 ** 2
            for sx, sy in pose_feet["seated"]
        )
        if is_staff:
            zone = "staff"
            state = "working"
        elif is_waiting:
            zone = "waiting"
            state = "queue"
        elif is_seated:
            zone = "seating"
            state = "seated"
        else:
            zone = zk
            state = "unknown"
        position = {
            "x": int(fx), "y": int(fy),
            "zone": zone,
            "type": "staff" if is_staff else "customer",
            "state": state,
        }
        if track_id is not None:
            position["track_id"] = int(track_id)
        out.append(position)
    return out


def track_people(ft_model, frames, staff_accum=None, staff_zone=None):
    """연속 프레임을 추적하고 마지막 프레임의 박스와 ID를 반환한다.

    세그먼트 경계에서도 같은 모델 인스턴스에 persist=True를 유지하므로
    동일 인물의 ID가 다음 디지털 트윈 프레임까지 이어진다.
    staff_accum(Counter)을 주면 프레임마다 직원구역 안 track_id 체류를 누적한다.
    """
    result = None
    for path in frames:
        frame = read(path)
        if frame is None:
            continue
        result = ft_model.track(
            frame,
            persist=True,
            tracker=TRACKER_CONFIG,
            classes=[0],
            conf=0.30,
            iou=0.5,
            agnostic_nms=True,
            verbose=False,
        )[0]
        if staff_accum is not None and staff_zone and result.boxes.id is not None:
            fids = result.boxes.id.cpu().numpy().astype(int)
            fboxes = result.boxes.xyxy.cpu().numpy()
            for tid, b in zip(fids, fboxes):
                if assign_zone(foot_point(b), staff_zone) is not None:
                    staff_accum[int(tid)] += 1

    if result is None or result.boxes is None:
        return np.empty((0, 4)), []

    boxes = result.boxes.xyxy.cpu().numpy()
    if result.boxes.id is None:
        return boxes, [None] * len(boxes)
    return boxes, result.boxes.id.cpu().numpy().astype(int).tolist()


def runtime_zones(store_id: str, camera_id: str, width: int, height: int):
    """배치는 ROI를 고정하고 LIVE는 승인 버전을 주기적으로 다시 확인한다."""
    key = (store_id, camera_id, width, height)
    cached = _ZONE_CACHE.get(key)
    checked_at = time.monotonic()
    if cached is not None:
        age = checked_at - cached["checked_at"]
        if not ROI_AUTO_REFRESH or age < ROI_REFRESH_SECONDS:
            return cached["zones"]

    data, source = load_roi_zone_data(
        api_base_url=ROI_API_BASE_URL,
        store_id=store_id,
        camera_id=camera_id,
        frame_width=width,
        frame_height=height,
        cache_path=ROI_CACHE_DIR / f"{store_id}_{camera_id}.json",
        legacy_path=ZONES_DIR / f"{store_id}_zones.json",
    )
    _, zones = parse_zones(data)
    version = data.get("version")

    if cached is None:
        suffix = f" v{version}" if version is not None else ""
        print(f"  ROI {store_id}/{camera_id}: {source}{suffix}")
    elif cached["version"] != version or cached["source"] != source:
        previous = (
            f"{cached['source']} v{cached['version']}"
            if cached["version"] is not None
            else cached["source"]
        )
        current = f"{source} v{version}" if version is not None else source
        print(f"  ROI 갱신 {store_id}/{camera_id}: {previous} -> {current}")

    _ZONE_CACHE[key] = {
        "zones": zones,
        "source": source,
        "version": version,
        "checked_at": checked_at,
    }
    return zones


def analyze_and_render(ft_model, pose_model, store, seg, staff_accum=None):
    """매장 한 세그먼트 → (마지막프레임 주석 이미지, 집계). 이미지·상태 공통 경로.

    - 인원: 파인튜닝 모델(정확). - 대기: pose+dwell(서있는 대기자만).
    - 직원: staff_accum(Counter) 주면 '직원구역 누적 체류 top-K(STAFF_COUNT)' 인물만
      직원으로 세고, 없으면 직원구역 소속으로 센다(스냅샷 등).
    - 대기자만 주황으로 칠해 앉은 사람 오표시 없음. 헤더=집계와 일치.
    - c["positions"]: 사람별 좌표(디지털 트윈용, 이미지 픽셀).
    """
    frames = seg_frames(store["clip"], seg)
    if not frames:
        raise SystemExit(f"{store['store_id']} 세그 {seg} 프레임 없음")
    first_image = read(frames[0])
    if first_image is None:
        raise SystemExit(f"{store['store_id']} 세그 {seg} 이미지 디코드 실패")
    height, width = first_image.shape[:2]
    camera_id = f"{store['store_id']}-cam1"
    zones = runtime_zones(store["store_id"], camera_id, width, height)
    staff_zone = [z for z in zones if z["key"] == "staff"]
    last_path, pose_feet = pose_state_feet(pose_model, zones, frames)
    img = read(last_path)
    raw_img = img.copy()
    quality = frame_quality(img)
    ft_boxes, track_ids = track_people(ft_model, frames, staff_accum, staff_zone)
    staff_set = None
    if staff_accum is not None:
        k = STAFF_COUNT.get(store["store_id"], 1)
        staff_set = {t for t, cnt in staff_accum.most_common(k) if cnt > 0}
    c = render_analysis(img, zones, ft_boxes, pose_feet, track_ids, staff_set)
    _header(img, f"{store['store_id']}  customer {c['customers']}  "
                 f"wait {c['waiting']}  staff {c['staff']}  [{quality}]")
    c["quality"] = quality
    c["positions"] = person_positions(
        ft_boxes,
        zones,
        pose_feet,
        track_ids,
        staff_set,
    )
    return img, raw_img, c


def run_snapshot(seg_override=None):
    ft_models = load_store_trackers()
    pose = YOLO(POSE_MODEL)
    print(f"=== 분석 스냅샷 생성 → {SNAP_DIR} ===")
    for store in STORES:
        seg = seg_override or SNAP_SEG.get(store["store_id"], "0")
        img, _, c = analyze_and_render(
            ft_models[store["store_id"]], pose, store, seg
        )
        p = save_snapshot(store["store_id"], img)
        print(f"  {store['store_id']} (seg {seg}): 손님 {c['customers']} "
              f"대기 {c['waiting']} 직원 {c['staff']} [{c['quality']}] → {p.name}")


def reset_store_trackers(models):
    """재생을 처음으로 돌릴 때 매장별 ByteTrack 상태도 초기화한다."""
    for model in models.values():
        predictor = getattr(model, "predictor", None)
        trackers = getattr(predictor, "trackers", None) or []
        for tracker in trackers:
            reset = getattr(tracker, "reset", None)
            if callable(reset):
                reset()


def run_live(api, interval, limit=None, loop=False):
    """(ㄴ) 이미지↔상태 동기 재생. 세그먼트마다 분석 이미지 + StoreState를 함께 생성.

    같은 세그먼트에서 이미지(탐지+ROI, 대기자만 주황)와 상태(인원/대기/직원)를 만들어
    outputs/snapshots/<store>.jpg 갱신 + API로 POST → 이미지와 숫자가 항상 일치.
    모델·GPU·데이터가 있는 머신에서 실행하고, 백엔드가 SNAP_DIR을 서빙한다.

    실행: py cafe_stores.py --live --post http://localhost:8000 --interval 3
    """
    import urllib.request

    ft_models = load_store_trackers()
    pose = YOLO(POSE_MODEL)
    seg_map = {s["store_id"]: seg_dirs(s["clip"]) for s in STORES}
    n = min(len(v) for v in seg_map.values())
    if limit:
        n = min(n, limit)
    url = api.rstrip("/") + "/internal/store-states"
    staff_accum = {s["store_id"]: collections.Counter() for s in STORES}
    print(f"=== LIVE 동기 재생: {n}세그 × {len(STORES)}매장 → {url} (간격 {interval}s) ===")
    print("이미지 갱신: " + str(SNAP_DIR) + "\n중단 Ctrl+C\n")

    cycle = 0
    try:
        while True:
            if cycle:
                reset_store_trackers(ft_models)
                for accumulator in staff_accum.values():
                    accumulator.clear()  # 트래커 리셋 시 track_id도 초기화 → 누적도 초기화
                print(f"=== LIVE 재분석 {cycle + 1}회차 시작 ===")

            for t in range(n):
                for store in STORES:
                    seg = seg_map[store["store_id"]][t]
                    if not seg_frames(store["clip"], seg):
                        continue
                    img, raw_img, c = analyze_and_render(
                        ft_models[store["store_id"]], pose, store, seg,
                        staff_accum[store["store_id"]],
                    )
                    save_snapshot(store["store_id"], img)   # 로컬 디버그용
                    try:                                     # 이미지 API 업로드(#85)
                        upload_snapshot(api, store["store_id"], img)
                        upload_snapshot(api, store["store_id"], raw_img, raw=True)
                    except Exception as exc:  # noqa: BLE001
                        print(f"  이미지 업로드 실패({store['store_id']}): {exc}")
                    state = build_store_state(
                        {"staff": c["staff"], "waiting": c["waiting"]}, c["customers"],
                        c["waiting"], camera_id=f"{store['store_id']}-cam1",
                        store_id=store["store_id"], quality=c["quality"],
                        captured_at=datetime.now(KST))
                    state["model_version"] = active_model_version()
                    state_with_positions = {**state, "positions": c["positions"]}
                    occupancy = prepare_occupancy(
                        state_with_positions,
                        preserve_timestamp=True,
                        frame_width=raw_img.shape[1],
                        frame_height=raw_img.shape[0],
                    )
                    req = urllib.request.Request(
                        url, data=json.dumps(state).encode("utf-8"),
                        headers={"Content-Type": "application/json"}, method="POST")
                    try:
                        urllib.request.urlopen(req, timeout=5).close()
                    except Exception as exc:  # noqa: BLE001
                        print(f"  POST 실패({store['store_id']}): {exc}")
                    occupancy_url = (
                        api.rstrip("/")
                        + f"/internal/stores/{store['store_id']}/occupancy"
                    )
                    try:
                        post_state(occupancy_url, occupancy)
                    except Exception as exc:  # noqa: BLE001
                        print(f"  위치 POST 실패({store['store_id']}): {exc}")
                if t % 10 == 0:
                    print(f"  세그 {t + 1}/{n} 상태+이미지 갱신")
                if t < n - 1 or loop:
                    time.sleep(interval)

            if not loop:
                break
            cycle += 1
    except KeyboardInterrupt:
        print("\n중단됨")


def main():
    global ROI_API_BASE_URL, ROI_AUTO_REFRESH
    ap = argparse.ArgumentParser(description="CAFE 다매장 인원·대기·직원 집계(dwell)")
    ap.add_argument("--limit", type=int, default=None, help="매장별 앞 N세그만(빠른 확인)")
    ap.add_argument("--post", default=None, help="API 베이스 URL로 전송(예: http://localhost:8000)")
    ap.add_argument("--snapshot", action="store_true",
                    help="매장별 분석 이미지(탐지+ROI)를 outputs/snapshots/에 1장 생성")
    ap.add_argument("--snapshot-seg", default=None, help="스냅샷에 쓸 세그먼트 번호(전 매장 공통)")
    ap.add_argument("--live", action="store_true",
                    help="이미지↔상태 동기 재생: 세그먼트마다 이미지 갱신 + StoreState POST")
    ap.add_argument("--loop", action="store_true",
                    help="마지막 세그먼트 뒤 처음부터 LIVE 분석을 계속 반복")
    ap.add_argument("--interval", type=float, default=3.0, help="--live 세그먼트 간격(초)")
    ap.add_argument("--no-images", action="store_true",
                    help="상태만 생성하고 분석 이미지(frames/)는 저장하지 않음")
    args = ap.parse_args()
    ROI_API_BASE_URL = args.post or ROI_API_BASE_URL
    ROI_AUTO_REFRESH = args.live
    _ZONE_CACHE.clear()

    if args.snapshot:
        run_snapshot(args.snapshot_seg)
        return

    if args.live:
        if not args.post:
            raise SystemExit("--live 에는 --post <API URL> 이 필요합니다 (예: --post http://localhost:8000)")
        run_live(args.post, args.interval, args.limit, args.loop)
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
