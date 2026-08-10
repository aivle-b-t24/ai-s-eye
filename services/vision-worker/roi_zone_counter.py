"""ROI 구역별 인원 집계 파이프라인 (비전 파트 / 역할 B).

흐름: YOLO11s 사람 탐지 -> 발 위치와 bbox 하단 중첩으로 구역 판정
      -> 구역별 인원 집계 + 혼잡도 -> 시각화 + 클라우드 전송 JSON(store_state) 생성.

전송 JSON은 packages/contracts/store_state.schema.json 계약을 따른다.

사용 예:
    py services/vision-worker/roi_zone_counter.py                 # 기본값(CAFE store-001)으로 1장 실행
    py services/vision-worker/roi_zone_counter.py --image <경로>  # 다른 이미지
    py services/vision-worker/roi_zone_counter.py --no-show       # 창 없이 파일만 저장
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

# --- 기본 경로 (CAFE store-001 기준, 인자로 덮어쓸 수 있음) -----------------
DEFAULT_IMG_DIR = Path(r"D:\Cafe_Dataset\Cafe_Dataset\Dataset\cafe\5\0\images")
DEFAULT_IMAGE = DEFAULT_IMG_DIR / "frames_0.jpg"
DEFAULT_ZONES = Path(__file__).resolve().parent / "zones" / "store-001_zones.json"
OUT_DIR = Path(__file__).resolve().parent / "outputs"  # .gitignore의 outputs/ 규칙으로 자동 제외

# --- 구역 이름(한글) -> 전송 스키마용 영문 키 -----------------------------
ZONE_KEY = {"좌석": "seating", "카운터": "counter", "통로": "aisle",
            "직원": "staff", "대기": "waiting", "입구": "entrance"}
# 대기 인원(queue): 대기 구역이 있으면 그걸, 없으면 카운터(주문)로 근사
QUEUE_KEY_PRIORITY = ["waiting", "counter"]
STAFF_KO = "직원"          # 직원 구역(고객 집계에서 제외)

# 구역별 색상 (BGR)
ZONE_COLOR = {
    "seating": (255, 170, 0),   # 파랑 계열
    "counter": (0, 165, 255),   # 주황
    "aisle": (0, 200, 0),       # 초록
    "staff": (200, 0, 200),     # 보라(직원)
    "waiting": (0, 80, 255),    # 빨강 계열(대기 줄)
    "entrance": (180, 180, 0),  # 청록(출입구)
    "unknown": (150, 150, 150),  # 회색(미배정)
}
KST = timezone(timedelta(hours=9))


def parse_zones(data):
    """구역 데이터 객체를 OpenCV 폴리곤 형식으로 변환한다."""
    zones = []
    seq: dict[str, int] = {}
    for z in data.get("zones", []):
        pts = np.array(z["polygon"], dtype=np.int32)
        key = ZONE_KEY.get(z["name"], z["name"])  # 카테고리(집계용)
        seq[key] = seq.get(key, 0) + 1
        zid = f"{key}_{seq[key]}"                  # 개별 구역 고유 id(테이블별 좌석 등)
        cx = int(pts[:, 0].mean())
        cy = int(pts[:, 1].mean())
        zones.append({"name_ko": z["name"], "key": key, "zid": zid,
                      "polygon": pts, "center": (cx, cy)})
    return data, zones


def load_zones(path: Path):
    """zones JSON 로드. AI Hub 계열 JSON은 BOM이 있어 utf-8-sig로 읽는다."""
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)
    return parse_zones(data)


def foot_point(box) -> tuple[int, int]:
    """bbox(x1,y1,x2,y2) -> 발 위치(아래 중앙)."""
    x1, y1, x2, y2 = box
    return int((x1 + x2) / 2), int(y2)


def assign_zone(pt, zones):
    """발 위치가 속한 첫 구역(zone dict) 반환. 없으면 None."""
    for z in zones:
        if cv2.pointPolygonTest(z["polygon"], (float(pt[0]), float(pt[1])), False) >= 0:
            return z
    return None


def bbox_zone_overlap_ratio(box, zones, *, columns: int = 5, rows: int = 5) -> float:
    """bbox 중앙~하단의 표본점 중 ROI 안에 들어가는 비율을 반환한다.

    실제 polygon clipping보다 훨씬 단순하지만 카운터에 가려진 사람의 상체/하체 bbox가
    직원 ROI에 걸치는지 판정하기에는 충분하다.
    """
    if not zones or columns <= 0 or rows <= 0:
        return 0.0
    x1, y1, x2, y2 = map(float, box)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    # 머리만 ROI에 걸친 경우를 제외하고 몸통 아래 65%만 사용한다.
    sample_y1 = y1 + (y2 - y1) * 0.35
    xs = np.linspace(x1, x2, columns + 2)[1:-1]
    ys = np.linspace(sample_y1, y2, rows + 2)[1:-1]
    inside = 0
    total = columns * rows
    for x in xs:
        for y in ys:
            if assign_zone((x, y), zones) is not None:
                inside += 1
    return inside / total


def staff_zone_evidence(box, zones, *, overlap_threshold: float = 0.30) -> dict:
    """발 또는 bbox 중첩으로 직원 후보 여부와 근거를 반환한다."""
    staff_zones = [zone for zone in zones if zone["key"] == "staff"]
    foot_inside = assign_zone(foot_point(box), staff_zones) is not None
    overlap_ratio = bbox_zone_overlap_ratio(box, staff_zones)
    return {
        "candidate": foot_inside or overlap_ratio >= overlap_threshold,
        "foot_inside": foot_inside,
        "overlap_ratio": overlap_ratio,
    }


def congestion_level(count: int) -> str:
    """구역 인원 -> 혼잡도 라벨(시각화용, 임시 규칙)."""
    if count == 0:
        return "empty"
    if count <= 2:
        return "low"
    if count <= 5:
        return "medium"
    return "high"


def draw(img, zones, detections, zone_counts, zone_person, store_count, raw_count):
    """구역 폴리곤 + 발 위치 + 구역별 집계를 이미지에 그린다."""
    overlay = img.copy()
    for z in zones:
        color = ZONE_COLOR.get(z["key"], ZONE_COLOR["unknown"])
        cv2.fillPoly(overlay, [z["polygon"]], color)
    cv2.addWeighted(overlay, 0.25, img, 0.75, 0, img)
    # 구역 테두리: 좌석은 점유 시 흰 두꺼운 선, 빈자리는 얇은 선으로 구분
    for z in zones:
        color = ZONE_COLOR.get(z["key"], ZONE_COLOR["unknown"])
        occupied = zone_person.get(z["zid"], 0) > 0
        border = (255, 255, 255) if (z["key"] == "seating" and occupied) else color
        cv2.polylines(img, [z["polygon"]], True, border, 3 if occupied else 1)
        # 좌석 구역에 번호 + 점유 표시
        if z["key"] == "seating":
            n = zone_person.get(z["zid"], 0)
            tag = f"{z['zid'].split('_')[1]}:{'O' if n else 'X'}"
            cv2.putText(img, tag, z["center"], cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (0, 0, 0), 4)
            cv2.putText(img, tag, z["center"], cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (255, 255, 255), 2)

    # 탐지 발 위치 표시
    for det in detections:
        pt = det["foot"]
        key = det["key"] or "unknown"
        color = ZONE_COLOR.get(key, ZONE_COLOR["unknown"])
        x1, y1, x2, y2 = det["box"]
        cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), color, 1)
        cv2.circle(img, pt, 6, color, -1)
        cv2.circle(img, pt, 6, (0, 0, 0), 1)

    # 좌상단 집계 패널
    lines = [f"in-store: {store_count}  (raw {raw_count})"]
    for key, cnt in zone_counts.items():
        lines.append(f"{key}: {cnt} ({congestion_level(cnt)})")
    seat_zones = [z for z in zones if z["key"] == "seating"]
    if seat_zones:
        occ = sum(1 for z in seat_zones if zone_person.get(z["zid"], 0) > 0)
        lines.append(f"seats occupied: {occ}/{len(seat_zones)}")
    y = 30
    for line in lines:
        cv2.putText(img, line, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4)
        cv2.putText(img, line, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        y += 34
    return img


def build_store_state(zone_counts, total, queue_count, camera_id, store_id, quality,
                      captured_at=None):
    """계약(store_state.schema.json)에 맞는 전송 JSON 생성.

    captured_at: 지정하면 그 시각을 쓴다(배치 생성 시 프레임별 시각 부여용).
                 없으면 현재 시각.
    """
    return {
        "schema_version": "1.0",
        "store_id": store_id,
        "camera_id": camera_id,
        "captured_at": (captured_at or datetime.now(KST)).isoformat(timespec="seconds"),
        "visible_person_count": int(total),
        "queue_count_estimate": int(queue_count),
        "zone_counts": {k: int(v) for k, v in zone_counts.items()},
        "quality_status": quality,
        "source": "vision-worker",
        "model_version": "yolo11s",
    }


def process(image_path, zones_path, model_name, conf, iou, count_in_zone_only,
            store_id, camera_id, show, save_image=True):
    _, zones = load_zones(zones_path)
    # 스키마에 나올 구역 키를 0으로 초기화(사람이 없어도 키 유지)
    zone_counts = {z["key"]: 0 for z in zones}

    model = YOLO(model_name)
    # iou 낮춤 + agnostic NMS: 한 사람이 두 박스로 잡히는 중복 탐지 병합
    results = model.predict(
        str(image_path), classes=[0], conf=conf, iou=iou,
        agnostic_nms=True, verbose=False,
    )[0]

    img = cv2.imread(str(image_path))
    if img is None:
        # 한글 경로 대비: numpy로 디코드
        img = cv2.imdecode(np.fromfile(str(image_path), dtype=np.uint8), cv2.IMREAD_COLOR)

    zone_person = {z["zid"]: 0 for z in zones}  # 개별 구역별 인원(좌석 점유 판정용)
    detections = []
    for box in results.boxes.xyxy.cpu().numpy():
        pt = foot_point(box)
        z = assign_zone(pt, zones)
        if z is not None:
            zone_counts[z["key"]] += 1
            zone_person[z["zid"]] += 1
        detections.append({"box": box, "foot": pt,
                           "zid": z["zid"] if z else None,
                           "key": z["key"] if z else None})

    total_raw = len(detections)
    in_zone = sum(1 for d in detections if d["zid"] is not None)
    unassigned = total_raw - in_zone
    # 매장 구역 안 인원만 셀지(창밖/매장 밖 오탐 제외) 여부
    total = in_zone if count_in_zone_only else total_raw
    queue_count = next(
        (zone_counts[k] for k in QUEUE_KEY_PRIORITY if k in zone_counts), 0
    )
    # 탐지가 0이면 화질/각도 문제일 수 있어 low로 표기
    quality = "normal" if total > 0 else "low"

    # 좌석(테이블별) 점유: 좌석 카테고리 구역별로 사람 있으면 점유로 본다
    seat_zones = [z for z in zones if z["key"] == "seating"]
    seats_total = len(seat_zones)
    seats_occupied = sum(1 for z in seat_zones if zone_person[z["zid"]] > 0)

    state = build_store_state(
        zone_counts, total, queue_count, camera_id, store_id, quality
    )

    OUT_DIR.mkdir(exist_ok=True)
    stem = Path(image_path).stem
    # 주석 이미지는 저장(또는 창 표시)이 필요할 때만 그린다 — 배치 시 파일 폭증 방지
    annotated = None
    out_img = None
    if save_image or show:
        annotated = draw(img, zones, detections, zone_counts, zone_person, total, total_raw)
    if save_image:
        out_img = OUT_DIR / f"{stem}_roi.jpg"
        cv2.imencode(".jpg", annotated)[1].tofile(str(out_img))
    out_json = OUT_DIR / f"{stem}_state.json"
    out_json.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== 구역별 집계(카테고리) ===")
    for k, v in zone_counts.items():
        print(f"  {k:10s}: {v}  ({congestion_level(v)})")
    print(f"  탐지 총 {total_raw} / 매장 내 {in_zone} / 구역 밖(제외) {unassigned} / 대기(queue) {queue_count}")
    if seats_total:
        rate = seats_occupied / seats_total * 100
        print(f"=== 좌석 점유 ({seats_occupied}/{seats_total}, {rate:.0f}%) ===")
        for z in seat_zones:
            n = zone_person[z["zid"]]
            print(f"  {z['zid']:12s}: {'사람 ' + str(n) if n else '빈자리':8s}")
    print("=== 전송 JSON ===")
    print(json.dumps(state, ensure_ascii=False, indent=2))
    print(f"\n저장: {out_json}" + (f"\n      {out_img}" if out_img else " (이미지 생략)"))

    if show:
        disp = cv2.resize(annotated, None, fx=0.7, fy=0.7)
        cv2.imshow("ROI zone counting", disp)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    return state


def main():
    ap = argparse.ArgumentParser(description="ROI 구역별 인원 집계 + 전송 JSON 생성")
    ap.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    ap.add_argument("--zones", type=Path, default=DEFAULT_ZONES)
    ap.add_argument("--model", default="yolo11s.pt")
    ap.add_argument("--conf", type=float, default=0.30)
    ap.add_argument("--iou", type=float, default=0.5, help="NMS IoU(낮출수록 중복 박스 병합)")
    ap.add_argument("--count-all", dest="count_in_zone_only", action="store_false",
                    help="구역 밖 탐지도 총 인원에 포함(기본: 구역 안만 집계)")
    ap.add_argument("--store-id", default="store-001")
    ap.add_argument("--camera-id", default="store-001-cam1")
    ap.add_argument("--no-show", dest="show", action="store_false")
    ap.add_argument("--json-only", dest="save_image", action="store_false",
                    help="주석 이미지 저장 없이 JSON만 저장(배치용)")
    args = ap.parse_args()
    process(
        args.image, args.zones, args.model, args.conf, args.iou,
        args.count_in_zone_only, args.store_id, args.camera_id, args.show,
        args.save_image,
    )


if __name__ == "__main__":
    main()
