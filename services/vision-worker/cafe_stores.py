"""CAFE 다매장(프랜차이즈) 인원·대기·직원 집계 → 매장별 StoreState 시계열.

현재 프로젝트는 대표 매장 2곳(store-001, store-002)만 운영한다.
매장을 늘리려면 STORES에 항목을 추가하고 zones/<store_id>_zones.json 을 그린 뒤 다시 실행.

집계 방식(최신):
- 인원수(visible_person_count) = 파인튜닝 모델(best.pt) 탐지 - 직원 (= 손님)
- 대기(queue_count_estimate)   = 대기 구역 + 서있음(pose) + N프레임 체류(ByteTrack)
                                  → 그 세그먼트(시간 윈도) 동시 대기 인원
- 직원(zone_counts.staff)      = 직원 ROI 발/bbox 중첩 + track 다수결 → 손님에서 제외

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

from cafe_tracking import (
    EXPECTED_MODEL_SHA256,
    OutputSampler,
    TrackingEpoch,
    iter_camera_frames,
    load_scene_cuts,
    reset_ultralytics_tracker,
    validate_model_file,
)
from roi_zone_counter import (
    parse_zones, foot_point, assign_zone, build_store_state, staff_zone_evidence,
    ZONE_COLOR, KST,
)
from roi_config_client import load_roi_zone_data
from replay_states import internal_headers, post_state, prepare_occupancy

CAFE_ROOT = Path(os.getenv(
    "AISEYE_CAFE_ROOT", r"D:\Cafe_Dataset\Cafe_Dataset\Dataset\cafe"))
CAFE_MODEL = os.getenv("AISEYE_CAFE_MODEL", "")
POSE_MODEL = "yolo11s-pose.pt"   # 자동 다운로드(서있음/앉음 + 추적)
TRACKING_PROFILE = os.getenv("AISEYE_TRACKING_PROFILE", "baseline")
if TRACKING_PROFILE not in {"baseline", "candidate"}:
    raise ValueError("AISEYE_TRACKING_PROFILE은 baseline 또는 candidate여야 합니다")
TRACKER_CONFIG = os.getenv(
    "AISEYE_TRACKER",
    (
        str(Path(__file__).resolve().parent / "trackers" / "bytetrack_cafe.yaml")
        if TRACKING_PROFILE == "candidate"
        else "bytetrack.yaml"
    ),
)
MODEL_VERSION = "yolo11s-cafe-ft+pose-dwell"
MODEL_SHA256 = os.getenv("AISEYE_CAFE_MODEL_SHA256", EXPECTED_MODEL_SHA256)
SCENE_CUTS_PATH = Path(__file__).resolve().parent / "cafe_scene_cuts.json"
DETECTION_CONFIDENCE = float(os.getenv(
    "AISEYE_DETECTION_CONFIDENCE",
    "0.10" if TRACKING_PROFILE == "candidate" else "0.30",
))
OUTPUT_INTERVAL_SECONDS = 1.0
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

# 직원 ROI는 카메라 원근과 카운터 가림 정도가 달라 같은 기준을 공유할 수 없다.
# store-001은 겹침이 큰 bbox만 보완 근거로 쓴다. store-002는 카운터에 가려진
# 직원 bbox도 받아들이되, 한 번 확정한 직원 ID 하나만 유지해 주문 고객이 함께
# 직원으로 집계되는 것을 막는다. 현재 두 데모 영상의 실제 근무 인원은 한 명이다.
STAFF_ROLE_POLICIES = {
    "store-001": {"use_bbox": True, "bbox_overlap_threshold": 0.80},
    "store-002": {
        "use_bbox": True,
        "bbox_overlap_threshold": 0.20,
        "max_active_staff": 1,
        "locked_bbox_overlap_threshold": 0.20,
        "lock_grace_updates": 10,
    },
}
# 온보딩 매장(store-003+)용 기본값: staff ROI 발 위치 + 중간 bbox 겹침
DEFAULT_STAFF_ROLE_POLICY = {"use_bbox": True, "bbox_overlap_threshold": 0.35}


def staff_role_policy(store_id: str) -> dict:
    return STAFF_ROLE_POLICIES.get(store_id, DEFAULT_STAFF_ROLE_POLICY)


def staff_candidates(boxes, zones, store_id: str) -> list[bool]:
    policy = staff_role_policy(store_id)
    result = []
    for box in boxes:
        evidence = staff_zone_evidence(
            box,
            zones,
            overlap_threshold=policy["bbox_overlap_threshold"],
        )
        result.append(
            bool(
                evidence["foot_inside"]
                or (policy["use_bbox"] and evidence["candidate"])
            )
        )
    return result


def read(path):
    return cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)


def load_cafe_model():
    """사람 탐지 모델 한 개를 만든다.

    추적 상태는 YOLO 인스턴스 내부에 유지되므로 카메라별로 별도 인스턴스를
    사용해야 서로 다른 매장의 track_id가 섞이지 않는다.
    """
    model_path = Path(CAFE_MODEL) if CAFE_MODEL else Path("<unset>")
    validate_model_file(model_path, MODEL_SHA256)
    return YOLO(model_path)


def active_model_version():
    """실제로 불러온 탐지 가중치에 맞는 버전을 반환한다."""
    return f"{MODEL_VERSION}-{TRACKING_PROFILE}@{MODEL_SHA256[:12]}"


def load_store_trackers():
    """운영 매장마다 독립된 사람 추적기를 준비한다."""
    model_path = Path(CAFE_MODEL) if CAFE_MODEL else Path("<unset>")
    digest = validate_model_file(model_path, MODEL_SHA256)
    print(f"CAFE 모델 확인: {model_path} (sha256 {digest[:12]}…)")
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
    staff = sum(1 for box in boxes if staff_zone_evidence(box, staff_zone)["candidate"])
    return len(boxes), staff, quality


def run(
    limit=None,
    gen_images=True,
    output_interval=OUTPUT_INTERVAL_SECONDS,
):
    """전 프레임 추적 후 영상 시간 간격에 맞춘 매장별 상태를 생성한다."""
    ft_models = load_store_trackers()
    pose = YOLO(POSE_MODEL)
    base = datetime.now(KST)
    if gen_images:
        FRAMES_DIR.mkdir(parents=True, exist_ok=True)
        RAW_FRAMES_DIR.mkdir(parents=True, exist_ok=True)

    timelines = {}
    for store in STORES:
        store_id = store["store_id"]
        timeline = []
        print(f"=== {store_id} 카메라 {store['clip']} 연속 추적 ===")
        for k, state, img, raw_img in analyze_store_stream(
            ft_models[store_id],
            pose,
            store,
            base_time=base,
            output_interval=output_interval,
            segment_limit=limit,
        ):
            timeline.append(state)
            if gen_images:
                sdir = FRAMES_DIR / store_id
                raw_dir = RAW_FRAMES_DIR / store_id
                sdir.mkdir(parents=True, exist_ok=True)
                raw_dir.mkdir(parents=True, exist_ok=True)
                cv2.imencode(".jpg", img)[1].tofile(str(sdir / f"{k:04d}.jpg"))
                cv2.imencode(".jpg", raw_img)[1].tofile(
                    str(raw_dir / f"{k:04d}.jpg")
                )
            if (k + 1) % 100 == 0:
                print(f"  출력 {k + 1}건{', 이미지 저장' if gen_images else ''}")
        timelines[store_id] = timeline
        print(f"  완료: {len(timeline)}건")

    states = []
    longest = max((len(timeline) for timeline in timelines.values()), default=0)
    for index in range(longest):
        for store in STORES:
            timeline = timelines[store["store_id"]]
            if index < len(timeline):
                states.append(timeline[index])
    return states


def _header(img, text):
    cv2.putText(img, text, (14, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 6)
    cv2.putText(img, text, (14, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)


def save_snapshot(store_id, img):
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SNAP_DIR / f"{store_id}.jpg"
    cv2.imencode(".jpg", img)[1].tofile(str(out_path))
    return out_path


def upload_snapshot(api, store_id, img, *, raw=False, metadata=None):
    """분석 이미지 또는 ROI 설정용 원본을 백엔드에 업로드한다.

    분석본: POST /internal/stores/{store_id}/vision-snapshot
    원본:   POST /internal/stores/{store_id}/vision-raw
    """
    import urllib.request
    jpg = cv2.imencode(".jpg", img)[1].tobytes()
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
        + jpg
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


def render_analysis(
    img,
    zones,
    ft_boxes,
    pose_feet,
    track_ids=None,
    staff_flags=None,
):
    """FT 탐지 박스 + 직원/대기 ROI를 그린다. 발점 색은 dwell 기준으로 통일:
       직원=보라, (대기자 발 위치 근처)=주황, 그 외=파랑(좌석/기타).
       직원 판정: 발 또는 bbox 중첩과, LIVE에서는 track 다수결 결과.
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
    if staff_flags is None:
        staff_flags = [
            staff_zone_evidence(box, zones)["candidate"] for box in ft_boxes
        ]
    if len(staff_flags) != len(ft_boxes):
        raise ValueError("staff_flags and boxes must have the same length")
    for b, track_id, is_staff in zip(ft_boxes, track_ids, staff_flags):
        foot = foot_point(b)
        z = assign_zone(foot, zones)
        zk = z["key"] if z else None
        near_waiter = any((foot[0] - wx) ** 2 + (foot[1] - wy) ** 2 < 70 ** 2
                          for wx, wy in pose_feet["waiting"])
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
            track_label = str(track_id).rsplit(":", 1)[-1]
            cv2.putText(
                img,
                f"ID {track_label}",
                (int(b[0]), max(int(b[1]) - 6, 16)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (255, 255, 255),
                2,
            )
            cv2.putText(
                img,
                f"ID {track_label}",
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
    confidences=None,
    staff_flags=None,
):
    """FT 추적 → 사람별 ID·좌표·구역·유형. 디지털 트윈용.

    각 사람: {track_id, x, y(발 위치), zone, type}.
    직원 판정: 발 또는 bbox 중첩과, LIVE에서는 track 다수결 결과.
    """
    out = []
    track_ids = track_ids if track_ids is not None else [None] * len(ft_boxes)
    confidences = confidences if confidences is not None else [None] * len(ft_boxes)
    if staff_flags is None:
        staff_flags = [
            staff_zone_evidence(box, zones)["candidate"] for box in ft_boxes
        ]
    if len(track_ids) != len(ft_boxes):
        raise ValueError("track_ids and boxes must have the same length")
    if len(confidences) != len(ft_boxes):
        raise ValueError("confidences and boxes must have the same length")
    if len(staff_flags) != len(ft_boxes):
        raise ValueError("staff_flags and boxes must have the same length")
    for b, track_id, confidence, is_staff in zip(
        ft_boxes, track_ids, confidences, staff_flags
    ):
        fx, fy = foot_point(b)
        z = assign_zone((int(fx), int(fy)), zones)
        zk = z["key"] if z else None
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
            "bbox": {
                "x1": float(b[0]), "y1": float(b[1]),
                "x2": float(b[2]), "y2": float(b[3]),
            },
            "zone": zone,
            "type": "staff" if is_staff else "customer",
            "state": state,
        }
        if track_id is not None:
            position["track_id"] = str(track_id)
        if confidence is not None:
            position["confidence"] = round(float(confidence), 6)
        out.append(position)
    return out


def track_people(ft_model, frames):
    """연속 프레임을 추적하고 마지막 프레임의 박스와 ID를 반환한다.

    세그먼트 경계에서도 같은 모델 인스턴스에 persist=True를 유지하므로
    동일 인물의 ID가 다음 디지털 트윈 프레임까지 이어진다.
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
            conf=DETECTION_CONFIDENCE,
            iou=0.5,
            agnostic_nms=True,
            verbose=False,
        )[0]
    if result is None or result.boxes is None:
        return np.empty((0, 4)), [], []

    boxes = result.boxes.xyxy.cpu().numpy()
    confidences = result.boxes.conf.cpu().numpy().tolist()
    if result.boxes.id is None:
        return boxes, [None] * len(boxes), confidences
    return (
        boxes,
        result.boxes.id.cpu().numpy().astype(int).tolist(),
        confidences,
    )


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


def runtime_roi_identity(
    store_id: str,
    camera_id: str,
    width: int,
    height: int,
) -> tuple[int | None, str]:
    cached = _ZONE_CACHE.get((store_id, camera_id, width, height), {})
    return cached.get("version"), cached.get("source", "legacy")


def analyze_and_render(ft_model, pose_model, store, seg):
    """매장 한 세그먼트 → (마지막프레임 주석 이미지, 집계). 이미지·상태 공통 경로.

    - 인원: 파인튜닝 모델(정확). - 대기: pose+dwell(서있는 대기자만).
    - 직원: 직원 ROI의 발/bbox 중첩을 사용하며 LIVE에서는 track 다수결로 안정화한다.
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
    roi_version, roi_source = runtime_roi_identity(
        store["store_id"],
        camera_id,
        width,
        height,
    )
    last_path, pose_feet = pose_state_feet(pose_model, zones, frames)
    img = read(last_path)
    raw_img = img.copy()
    quality = frame_quality(img)
    ft_boxes, track_ids, confidences = track_people(ft_model, frames)
    staff_flags = staff_candidates(ft_boxes, zones, store["store_id"])
    c = render_analysis(
        img,
        zones,
        ft_boxes,
        pose_feet,
        track_ids,
        staff_flags,
    )
    _header(img, f"{store['store_id']}  customer {c['customers']}  "
                 f"wait {c['waiting']}  staff {c['staff']}  [{quality}]")
    c["quality"] = quality
    c["roi_version"] = roi_version
    c["roi_source"] = roi_source
    c["frame_width"] = width
    c["frame_height"] = height
    c["positions"] = person_positions(
        ft_boxes,
        zones,
        pose_feet,
        track_ids,
        confidences,
        staff_flags,
    )
    return img, raw_img, c


def _box_iou(first, second) -> float:
    left = max(float(first[0]), float(second[0]))
    top = max(float(first[1]), float(second[1]))
    right = min(float(first[2]), float(second[2]))
    bottom = min(float(first[3]), float(second[3]))
    intersection = max(right - left, 0.0) * max(bottom - top, 0.0)
    first_area = max(float(first[2] - first[0]), 0.0) * max(
        float(first[3] - first[1]), 0.0
    )
    second_area = max(float(second[2] - second[0]), 0.0) * max(
        float(second[3] - second[1]), 0.0
    )
    union = first_area + second_area - intersection
    return intersection / union if union > 0 else 0.0


def match_postures(detector_boxes, pose_result) -> list[str]:
    """Pose 박스를 주 추적 박스에 매칭해 자세만 가져온다."""
    matched = ["unknown"] * len(detector_boxes)
    if (
        pose_result is None
        or pose_result.boxes is None
        or pose_result.keypoints is None
        or pose_result.keypoints.xy is None
    ):
        return matched
    pose_boxes = pose_result.boxes.xyxy.cpu().numpy()
    keypoints = pose_result.keypoints.xy.cpu().numpy()
    confidences = (
        pose_result.keypoints.conf.cpu().numpy()
        if pose_result.keypoints.conf is not None
        else None
    )
    candidates = sorted(
        (
            (_box_iou(detector_box, pose_box), detector_index, pose_index)
            for detector_index, detector_box in enumerate(detector_boxes)
            for pose_index, pose_box in enumerate(pose_boxes)
        ),
        reverse=True,
    )
    used_detector = set()
    used_pose = set()
    for overlap, detector_index, pose_index in candidates:
        if overlap < 0.20:
            break
        if detector_index in used_detector or pose_index in used_pose:
            continue
        used_detector.add(detector_index)
        used_pose.add(pose_index)
        if confidences is not None:
            matched[detector_index] = posture(
                keypoints[pose_index], confidences[pose_index]
            )
    return matched


class PoseDwellState:
    """주 ByteTrack ID를 기준으로 대기·착석 자세 체류를 누적한다."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.waiting_stand = collections.Counter()
        self.waiting_sit = collections.Counter()
        self.seating_sit = collections.Counter()
        self.seating_stand = collections.Counter()

    def update(self, boxes, track_ids, postures, zones) -> dict[str, list]:
        waiting_feet = []
        seated_feet = []
        wait_zone = [zone for zone in zones if zone["key"] == "waiting"]
        seating_zone = [zone for zone in zones if zone["key"] == "seating"]
        for box, track_id, pose_name in zip(boxes, track_ids, postures):
            if track_id is None:
                continue
            foot = foot_point(box)
            if assign_zone(foot, wait_zone) is not None:
                if pose_name == "stand":
                    self.waiting_stand[track_id] += 1
                elif pose_name == "sit":
                    self.waiting_sit[track_id] += 1
                if (
                    pose_name == "stand"
                    and self.waiting_stand[track_id] >= N_DWELL
                    and self.waiting_stand[track_id]
                    > self.waiting_sit.get(track_id, 0)
                ):
                    waiting_feet.append(foot)
            if assign_zone(foot, seating_zone) is not None:
                if pose_name == "sit":
                    self.seating_sit[track_id] += 1
                elif pose_name == "stand":
                    self.seating_stand[track_id] += 1
                if (
                    pose_name == "sit"
                    and self.seating_sit[track_id] >= N_SEATED
                    and self.seating_sit[track_id]
                    > self.seating_stand.get(track_id, 0)
                ):
                    seated_feet.append(foot)
        return {"waiting": waiting_feet, "seated": seated_feet}


class StaffRoleState:
    """ROI 다수결과 선택적 직원 ID 고정으로 역할을 안정화한다.

    ``max_active_staff``를 설정하지 않으면 기존처럼 track별 최근 5회 중 3회
    ROI 근거만 사용한다. 값을 설정하면 근거가 강한 ID부터 제한 인원만 확정하고,
    짧은 bbox 가림 동안 다른 고객 ID로 역할이 튀는 것을 막는다.
    """

    def __init__(
        self,
        window_size: int = 5,
        required_votes: int = 3,
        *,
        max_active_staff: int | None = None,
        locked_bbox_overlap_threshold: float | None = None,
        lock_grace_updates: int = 10,
    ) -> None:
        if window_size <= 0 or not 1 <= required_votes <= window_size:
            raise ValueError("invalid staff vote window")
        if max_active_staff is not None and max_active_staff <= 0:
            raise ValueError("max_active_staff must be greater than zero")
        if lock_grace_updates < 0:
            raise ValueError("lock_grace_updates must not be negative")
        self.window_size = window_size
        self.required_votes = required_votes
        self.max_active_staff = max_active_staff
        self.locked_bbox_overlap_threshold = locked_bbox_overlap_threshold
        self.lock_grace_updates = lock_grace_updates
        self.reset()

    def reset(self) -> None:
        self.history: dict[int | str, collections.deque] = {}
        self.locked_track_ids: set[int | str] = set()
        self.lock_missing_updates: collections.Counter = collections.Counter()

    def update(
        self,
        boxes,
        track_ids,
        zones,
        *,
        use_bbox: bool = True,
        bbox_overlap_threshold: float = 0.30,
    ) -> list[bool]:
        if len(boxes) != len(track_ids):
            raise ValueError("track_ids and boxes must have the same length")
        evidences = [
            staff_zone_evidence(
                box,
                zones,
                overlap_threshold=bbox_overlap_threshold,
            )
            for box in boxes
        ]
        return self.update_evidence(
            evidences,
            track_ids,
            use_bbox=use_bbox,
            bbox_overlap_threshold=bbox_overlap_threshold,
        )

    def update_evidence(
        self,
        evidences: list[dict],
        track_ids,
        *,
        use_bbox: bool = True,
        bbox_overlap_threshold: float = 0.30,
    ) -> list[bool]:
        """저장된 ROI 근거에도 실시간과 동일한 역할 상태를 적용한다."""
        if len(evidences) != len(track_ids):
            raise ValueError("track_ids and evidences must have the same length")
        flags = []
        details = []
        for evidence, track_id in zip(evidences, track_ids):
            candidate = bool(
                evidence["foot_inside"]
                or (
                    use_bbox
                    and float(evidence["overlap_ratio"])
                    >= bbox_overlap_threshold
                )
            )
            if track_id is None:
                flags.append(candidate)
                details.append((track_id, evidence, int(candidate)))
                continue
            history = self.history.setdefault(
                track_id,
                collections.deque(maxlen=self.window_size),
            )
            history.append(candidate)
            votes = sum(history)
            flags.append(votes >= self.required_votes)
            details.append((track_id, evidence, votes))

        if self.max_active_staff is None:
            return flags

        visible_by_id = {
            track_id: (index, evidence)
            for index, (track_id, evidence, _) in enumerate(details)
            if track_id is not None
        }
        selected_indices = set()
        expired_locks = set()
        keep_threshold = (
            bbox_overlap_threshold
            if self.locked_bbox_overlap_threshold is None
            else self.locked_bbox_overlap_threshold
        )
        for track_id in self.locked_track_ids:
            visible = visible_by_id.get(track_id)
            if visible is None:
                self.lock_missing_updates[track_id] += 1
            else:
                index, evidence = visible
                keep = bool(
                    evidence["foot_inside"]
                    or (use_bbox and evidence["overlap_ratio"] >= keep_threshold)
                )
                if keep:
                    self.lock_missing_updates[track_id] = 0
                    selected_indices.add(index)
                else:
                    self.lock_missing_updates[track_id] += 1
            if self.lock_missing_updates[track_id] > self.lock_grace_updates:
                expired_locks.add(track_id)

        self.locked_track_ids.difference_update(expired_locks)
        for track_id in expired_locks:
            del self.lock_missing_updates[track_id]

        open_slots = self.max_active_staff - len(self.locked_track_ids)
        if open_slots > 0:
            candidates = []
            for index, ((track_id, evidence, votes), is_staff) in enumerate(
                zip(details, flags)
            ):
                if (
                    track_id is None
                    or track_id in self.locked_track_ids
                    or not is_staff
                ):
                    continue
                candidates.append(
                    (
                        bool(evidence["foot_inside"]),
                        votes,
                        float(evidence["overlap_ratio"]),
                        -index,
                        track_id,
                        index,
                    )
                )
            for *_, track_id, index in sorted(candidates, reverse=True)[:open_slots]:
                self.locked_track_ids.add(track_id)
                self.lock_missing_updates[track_id] = 0
                selected_indices.add(index)

        return [index in selected_indices for index in range(len(flags))]


class StaffCountState:
    """같은 장면의 짧은 가림·ID 교체 동안 직전 직원 수를 유지한다."""

    def __init__(self, grace_updates: int = 10) -> None:
        if grace_updates < 0:
            raise ValueError("staff count grace must not be negative")
        self.grace_updates = grace_updates
        self.reset()

    def reset(self) -> None:
        self.last_count = 0
        self.missing_updates = 0

    def update(self, observed_count: int) -> int:
        if observed_count < 0:
            raise ValueError("observed staff count must not be negative")
        if observed_count > 0:
            self.last_count = observed_count
            self.missing_updates = 0
            return observed_count
        self.missing_updates += 1
        if self.last_count > 0 and self.missing_updates <= self.grace_updates:
            return self.last_count
        return 0


class StaffPresenceState:
    """직원 집계와 마지막 위치를 같은 가림 유예 시간으로 유지한다.

    직원 track이 사라진 경우에만 마지막 위치를 `occluded`로 보존한다. 같은 ID가
    충분히 멀리 이동한 채 고객으로 계속 보이면 실제 ROI 이탈로 보고 즉시 해제한다.
    """

    def __init__(
        self,
        grace_updates: int = 10,
        exit_distance_pixels: float = 120.0,
    ) -> None:
        if exit_distance_pixels <= 0:
            raise ValueError("staff exit distance must be greater than zero")
        self.exit_distance_pixels = float(exit_distance_pixels)
        self.counts = StaffCountState(grace_updates=grace_updates)
        self.reset()

    def reset(self) -> None:
        self.counts.reset()
        self.last_staff_positions: list[dict] = []

    @staticmethod
    def _copy_position(position: dict, *, occluded: bool = False) -> dict:
        copied = dict(position)
        if isinstance(position.get("bbox"), dict):
            copied["bbox"] = dict(position["bbox"])
        if occluded:
            copied["occluded"] = True
        else:
            copied.pop("occluded", None)
        return copied

    @staticmethod
    def _distance(left: dict, right: dict) -> float:
        return float(np.hypot(left["x"] - right["x"], left["y"] - right["y"]))

    def update(self, positions: list[dict]) -> tuple[list[dict], int]:
        current = [self._copy_position(position) for position in positions]
        observed_staff = [
            position for position in current if position.get("type") == "staff"
        ]
        if observed_staff:
            # ByteTrack이 짧은 가림 뒤 새 ID를 발급해도 같은 위치의 직원 아이콘은
            # 기존 공개 ID를 유지한다. 거리가 큰 경우에는 다른 사람일 수 있으므로
            # 연결하지 않는다.
            visible_ids = {
                position.get("track_id")
                for position in current
                if position.get("track_id") is not None
            }
            candidates = []
            for previous in self.last_staff_positions:
                previous_id = previous.get("track_id")
                if previous_id is None or previous_id in visible_ids:
                    continue
                for observed in observed_staff:
                    observed_id = observed.get("track_id")
                    if observed_id is None or observed_id == previous_id:
                        continue
                    distance = self._distance(previous, observed)
                    if distance <= self.exit_distance_pixels:
                        candidates.append((distance, previous, observed))
            used_previous_ids = set()
            used_observed_ids = set()
            for _, previous, observed in sorted(
                candidates, key=lambda item: item[0]
            ):
                previous_id = previous.get("track_id")
                observed_id = observed.get("track_id")
                if (
                    previous_id in used_previous_ids
                    or observed_id in used_observed_ids
                ):
                    continue
                observed["track_id"] = previous_id
                observed["relinked"] = True
                used_previous_ids.add(previous_id)
                used_observed_ids.add(observed_id)
            self.last_staff_positions = [
                self._copy_position(position) for position in observed_staff
            ]
            return current, self.counts.update(len(observed_staff))

        current_by_id = {
            position.get("track_id"): position
            for position in current
            if position.get("track_id") is not None
        }
        matched = [
            (previous, current_by_id[previous.get("track_id")])
            for previous in self.last_staff_positions
            if previous.get("track_id") in current_by_id
        ]
        if any(
            self._distance(previous, visible) > self.exit_distance_pixels
            for previous, visible in matched
        ):
            self.reset()
            return current, 0

        held_count = self.counts.update(0)
        if held_count == 0 or not self.last_staff_positions:
            self.last_staff_positions = []
            return current, 0

        held_ids = set()
        for previous, visible in matched:
            track_id = previous.get("track_id")
            held_ids.add(track_id)
            visible.update({
                "type": "staff",
                "state": "working",
                "zone": "staff",
                "occluded": True,
            })
        for previous in self.last_staff_positions:
            if previous.get("track_id") in held_ids:
                continue
            current.append(self._copy_position(previous, occluded=True))
        return current, held_count


def analyze_store_stream(
    ft_model,
    pose_model,
    store,
    *,
    base_time: datetime,
    output_interval: float = OUTPUT_INTERVAL_SECONDS,
    segment_limit: int | None = None,
):
    """약 5fps 전 프레임을 추적하고 영상 시간 1초 단위 상태를 생성한다."""
    camera_id = f"{store['store_id']}-cam1"
    scene_cuts = load_scene_cuts(SCENE_CUTS_PATH).get(str(store["clip"]), set())
    sampler = OutputSampler(output_interval)
    epoch = TrackingEpoch(camera_id)
    dwell = PoseDwellState()
    staff_policy = staff_role_policy(store["store_id"])
    staff_roles = StaffRoleState(
        max_active_staff=staff_policy.get("max_active_staff"),
        locked_bbox_overlap_threshold=staff_policy.get(
            "locked_bbox_overlap_threshold"
        ),
        lock_grace_updates=staff_policy.get("lock_grace_updates", 10),
    )
    staff_presence = StaffPresenceState()
    output_index = 0

    for sample in iter_camera_frames(
        CAFE_ROOT,
        str(store["clip"]),
        scene_cuts=scene_cuts,
        segment_limit=segment_limit,
    ):
        if sample.reset_before:
            reset_ultralytics_tracker(ft_model)
            dwell.reset()
            staff_roles.reset()
            staff_presence.reset()
            epoch.reset()

        frame = read(sample.path)
        if frame is None:
            continue
        height, width = frame.shape[:2]
        zones = runtime_zones(store["store_id"], camera_id, width, height)
        roi_version, _ = runtime_roi_identity(
            store["store_id"], camera_id, width, height
        )
        result = ft_model.track(
            frame,
            persist=True,
            tracker=TRACKER_CONFIG,
            classes=[0],
            conf=DETECTION_CONFIDENCE,
            iou=0.5,
            agnostic_nms=True,
            verbose=False,
        )[0]
        boxes = (
            result.boxes.xyxy.cpu().numpy()
            if result.boxes is not None
            else np.empty((0, 4))
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
        pose_result = pose_model.predict(
            frame,
            classes=[0],
            conf=0.30,
            iou=0.5,
            verbose=False,
        )[0]
        pose_feet = dwell.update(
            boxes,
            local_ids,
            match_postures(boxes, pose_result),
            zones,
        )
        should_emit = sampler.should_emit(
            sample.source_seconds,
            force=sample.reset_before and sample.reset_reason != "initial",
        )
        if not should_emit:
            continue

        staff_flags = staff_roles.update(
            boxes,
            local_ids,
            zones,
            use_bbox=staff_policy["use_bbox"],
            bbox_overlap_threshold=staff_policy["bbox_overlap_threshold"],
        )

        public_ids = [
            epoch.public_id(track_id) if track_id is not None else None
            for track_id in local_ids
        ]
        raw_img = frame.copy()
        image = frame.copy()
        quality = frame_quality(image)
        positions = person_positions(
            boxes,
            zones,
            pose_feet,
            public_ids,
            confidences,
            staff_flags,
        )
        positions, resolved_staff_count = staff_presence.update(positions)
        visible_staff_flags = [
            position.get("type") == "staff"
            for position in positions[: len(boxes)]
        ]
        counts = render_analysis(
            image,
            zones,
            boxes,
            pose_feet,
            public_ids,
            visible_staff_flags,
        )
        counts["staff"] = resolved_staff_count
        counts["customers"] = sum(
            position.get("type") != "staff" for position in positions
        )
        _header(
            image,
            f"{store['store_id']}  customer {counts['customers']}  "
            f"wait {counts['waiting']}  staff {counts['staff']}  [{quality}]",
        )
        captured_at = base_time + timedelta(seconds=sample.source_seconds)
        processed_at = datetime.now(KST)
        state = build_store_state(
            {"staff": counts["staff"], "waiting": counts["waiting"]},
            counts["customers"],
            counts["waiting"],
            camera_id=camera_id,
            store_id=store["store_id"],
            quality=quality,
            captured_at=captured_at,
        )
        state.update(
            {
                "model_version": active_model_version(),
                "frame_id": (
                    f"{store['store_id']}-s{sample.segment:04d}-"
                    f"f{sample.frame_number:04d}"
                ),
                "processed_at": processed_at.isoformat(),
                "roi_version": roi_version,
                "source": "vision-worker-stream",
                "source_seconds": round(sample.source_seconds, 6),
                "tracking_epoch": epoch.value,
                "tracking_reset": bool(sample.reset_before),
                "positions": positions,
            }
        )
        yield output_index, state, image, raw_img
        output_index += 1


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


def run_live(
    api,
    playback_speed,
    output_interval=OUTPUT_INTERVAL_SECONDS,
    limit=None,
    loop=False,
):
    """5fps 분석과 1초 출력을 유지하며 지정 속도로 LIVE 재생한다."""
    import urllib.request

    if playback_speed <= 0:
        raise ValueError("재생 속도는 0보다 커야 합니다")
    ft_models = load_store_trackers()
    pose = YOLO(POSE_MODEL)
    url = api.rstrip("/") + "/internal/store-states"
    wall_interval = output_interval / playback_speed
    print(
        f"=== LIVE 연속 추적: {len(STORES)}매장 → {url} "
        f"(영상 출력 {output_interval}s / 재생 {playback_speed:g}x) ==="
    )
    print("이미지 갱신: " + str(SNAP_DIR) + "\n중단 Ctrl+C\n")

    cycle = 0
    try:
        while True:
            if cycle:
                print(f"=== LIVE 재분석 {cycle + 1}회차 시작 ===")
            base_time = datetime.now(KST)
            streams = {
                store["store_id"]: analyze_store_stream(
                    ft_models[store["store_id"]],
                    pose,
                    store,
                    base_time=base_time,
                    output_interval=output_interval,
                    segment_limit=limit,
                )
                for store in STORES
            }
            tick = 0
            while True:
                tick_started = time.monotonic()
                batch = []
                for store in STORES:
                    try:
                        _, state, img, raw_img = next(streams[store["store_id"]])
                    except StopIteration:
                        batch = []
                        break
                    batch.append((store, state, img, raw_img))
                if not batch:
                    break

                for store, state, img, raw_img in batch:
                    save_snapshot(store["store_id"], img)
                    outgoing = state.copy()
                    for internal_key in (
                        "positions",
                        "source_seconds",
                        "tracking_epoch",
                        "tracking_reset",
                    ):
                        outgoing.pop(internal_key, None)
                    outgoing["source"] = "vision-worker-live"
                    metadata = {
                        key: outgoing.get(key)
                        for key in (
                            "schema_version",
                            "store_id",
                            "camera_id",
                            "frame_id",
                            "captured_at",
                            "processed_at",
                            "model_version",
                            "roi_version",
                            "source",
                        )
                    }
                    try:                                     # 이미지 API 업로드(#85)
                        upload_snapshot(
                            api,
                            store["store_id"],
                            img,
                            metadata=metadata,
                        )
                        upload_snapshot(
                            api,
                            store["store_id"],
                            raw_img,
                            raw=True,
                            metadata=metadata,
                        )
                    except Exception as exc:  # noqa: BLE001
                        print(f"  이미지 업로드 실패({store['store_id']}): {exc}")
                    occupancy = prepare_occupancy(
                        state,
                        preserve_timestamp=True,
                        frame_width=raw_img.shape[1],
                        frame_height=raw_img.shape[0],
                    )
                    req = urllib.request.Request(
                        url, data=json.dumps(outgoing).encode("utf-8"),
                        headers=internal_headers({"Content-Type": "application/json"}),
                        method="POST")
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
                tick += 1
                if tick % 10 == 0:
                    print(f"  영상 시간 {tick * output_interval:.0f}초 상태+이미지 갱신")
                elapsed = time.monotonic() - tick_started
                time.sleep(max(wall_interval - elapsed, 0.0))

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
    ap.add_argument(
        "--roi-api",
        default=None,
        help="배치 생성 중 승인 ROI만 조회할 API 주소",
    )
    ap.add_argument("--snapshot", action="store_true",
                    help="매장별 분석 이미지(탐지+ROI)를 outputs/snapshots/에 1장 생성")
    ap.add_argument("--snapshot-seg", default=None, help="스냅샷에 쓸 세그먼트 번호(전 매장 공통)")
    ap.add_argument("--live", action="store_true",
                    help="이미지↔상태 동기 재생: 세그먼트마다 이미지 갱신 + StoreState POST")
    ap.add_argument("--loop", action="store_true",
                    help="마지막 세그먼트 뒤 처음부터 LIVE 분석을 계속 반복")
    ap.add_argument(
        "--output-interval",
        type=float,
        default=OUTPUT_INTERVAL_SECONDS,
        help="영상 시간 기준 디지털 트윈 출력 간격(초, 기본 1)",
    )
    ap.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="--live 재생 배속. 분석 시간축과 별도로 적용(기본 1x)",
    )
    ap.add_argument(
        "--interval",
        type=float,
        default=None,
        help="호환용 LIVE 실제 전송 간격. 지정하면 --speed 대신 사용",
    )
    ap.add_argument("--no-images", action="store_true",
                    help="상태만 생성하고 분석 이미지(frames/)는 저장하지 않음")
    args = ap.parse_args()
    ROI_API_BASE_URL = args.roi_api or args.post or ROI_API_BASE_URL
    ROI_AUTO_REFRESH = args.live
    _ZONE_CACHE.clear()

    if args.snapshot:
        run_snapshot(args.snapshot_seg)
        return

    if args.live:
        if not args.post:
            raise SystemExit("--live 에는 --post <API URL> 이 필요합니다 (예: --post http://localhost:8000)")
        playback_speed = args.speed
        if args.interval is not None:
            if args.interval <= 0:
                raise SystemExit("--interval은 0보다 커야 합니다")
            playback_speed = args.output_interval / args.interval
        run_live(
            args.post,
            playback_speed,
            output_interval=args.output_interval,
            limit=args.limit,
            loop=args.loop,
        )
        return

    states = run(
        args.limit,
        gen_images=not args.no_images,
        output_interval=args.output_interval,
    )

    out = Path(__file__).resolve().parents[2] / "samples" / "cafe_stores_states.json"
    out.parent.mkdir(exist_ok=True)
    doc = {
        "note": ("CAFE 다매장(현재 store-001·002) 집계. 인원=파인튜닝 탐지-직원, "
                 "대기=대기구역+서있음+체류(ByteTrack), 직원=직원구역. "
                 "captured_at은 CAFE 영상 시간 기반 합성 시각(실측 아님). 약 5fps "
                 "전 프레임을 추적하고 기본 1초마다 상태를 낸다. 각 상태는 frame_id, "
                 "processed_at, 승인 roi_version, 장면 epoch 포함 track_id와 자세 state를 "
                 "포함한다. states 순서=분석 이미지 "
                 "outputs/snapshots/frames/<store_id>/{i:04d}.jpg 순서."),
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
                headers=internal_headers({"Content-Type": "application/json"}),
                method="POST")
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    ok += resp.status < 300
            except Exception as exc:  # noqa: BLE001
                print(f"  POST 실패({s['store_id']}): {exc}")
        print(f"POST {url} → 성공 {ok}/{len(states)}")


if __name__ == "__main__":
    main()
