"""다중 카메라 병합 → store-001 StoreState 1건 (066 외부/대기 + 067 실내/좌석).

명칭: 066 = 외부(입구·대기), 067 = 실내(좌석·주문·직원).

- 066(외부/대기)과 067(실내/좌석·주문·직원)은 외부/실내라 구역이 안 겹침
  → visible_person_count는 각 카메라 매장 내 인원의 합(중복 없음), zone_counts는 합집합.
- 데이터셋에 timestamp가 없어 '같은 프레임 번호 = 같은 시각'으로 간주(명시적 가정).
  실서비스에선 각 카메라의 실제 촬영 시각으로 정당하게 페어링.

실행:
    py services/vision-worker/merge_cameras.py --frame 6
    py services/vision-worker/merge_cameras.py --frame 6 --post http://localhost:8000
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from roi_zone_counter import (
    load_zones, foot_point, assign_zone, build_store_state,
    QUEUE_KEY_PRIORITY, OUT_DIR,
)

# 집계에 쓰는 카메라(안 겹치는 2개). image는 프레임번호로 완성.
CAMERAS = [
    {  # 066 = 외부(입구·대기)
        "camera_id": "cam-066",
        "img_dir": Path(r"D:\223.실내외 군중 특성 데이터\01-1.정식개방데이터\Training"
                        r"\01.원천데이터\TS_2.시나리오_66.Outdoor_까페노아066(662)"),
        "img_fmt": "Outdoor_까페노아066_{n:03d}.jpg",
        "zones": Path(r"C:\Users\chicb\Downloads\Outdoor_까페노아066_001_zones.json"),
    },
    {  # 067 = 실내(좌석·주문·직원)
        "camera_id": "cam-067",
        "img_dir": Path(r"D:\223.실내외 군중 특성 데이터\01-1.정식개방데이터\Training"
                        r"\01.원천데이터\TS_2.시나리오_67.Indoor_까페노아067(662)"),
        "img_fmt": "Indoor_까페노아067_{n:03d}.jpg",
        "zones": Path(r"C:\Users\chicb\Downloads\Indoor_까페노아067_006_zones.json"),
    },
]


def read_image(path: Path):
    return cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)


def analyze_one(cam, frame, model, conf, iou):
    """카메라 1대 분석 → {zone_counts, in_zone}."""
    _, zones = load_zones(cam["zones"])
    zone_counts = {z["key"]: 0 for z in zones}
    img_path = cam["img_dir"] / cam["img_fmt"].format(n=frame)
    if not img_path.exists():
        raise FileNotFoundError(img_path)
    img = read_image(img_path)
    res = model.predict(img, classes=[0], conf=conf, iou=iou,
                        agnostic_nms=True, verbose=False)[0]
    in_zone = 0
    for box in res.boxes.xyxy.cpu().numpy():
        z = assign_zone(foot_point(box), zones)
        if z is not None:
            zone_counts[z["key"]] += 1
            in_zone += 1
    return {"camera_id": cam["camera_id"], "zone_counts": zone_counts,
            "in_zone": in_zone, "image": img_path.name,
            "zones_file": cam["zones"].name}


def merge(results, store_id):
    """카메라별 결과 → 병합 StoreState."""
    merged: dict[str, int] = {}
    total = 0
    for r in results:
        for k, v in r["zone_counts"].items():
            merged[k] = merged.get(k, 0) + v  # 구역 안 겹침(겹치면 합)
        total += r["in_zone"]
    queue = next((merged[k] for k in QUEUE_KEY_PRIORITY if k in merged), 0)
    quality = "normal" if total > 0 else "low"
    cam_id = "+".join(r["camera_id"].replace("cam-", "") for r in results)
    state = build_store_state(merged, total, queue, f"cam-{cam_id}",
                              store_id, quality)
    return state


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", type=int, default=6, help="양 카메라 공통 프레임 번호")
    ap.add_argument("--conf", type=float, default=0.30)
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--store-id", default="store-001")
    ap.add_argument("--post", default=None, help="API 베이스 URL (예: http://localhost:8000)")
    args = ap.parse_args()

    model = YOLO("yolo11s.pt")
    results = [analyze_one(c, args.frame, model, args.conf, args.iou) for c in CAMERAS]

    print(f"=== 카메라별 (frame {args.frame}, 같은 시각 간주) ===")
    for r in results:
        print(f"  {r['camera_id']}: 이미지 {r['image']} (구역 {r['zones_file']})")
        print(f"           매장내 {r['in_zone']}  {r['zone_counts']}")

    state = merge(results, args.store_id)
    OUT_DIR.mkdir(exist_ok=True)
    out_json = OUT_DIR / f"merged_frame{args.frame:03d}_state.json"
    out_json.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=== 병합 StoreState ===")
    print(json.dumps(state, ensure_ascii=False, indent=2))
    print(f"저장: {out_json}")

    if args.post:
        import urllib.request
        url = args.post.rstrip("/") + "/internal/store-states"
        body = json.dumps(state).encode("utf-8")
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(f"POST {url} → {resp.status}")


if __name__ == "__main__":
    main()
