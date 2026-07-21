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
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from roi_zone_counter import (
    load_zones, foot_point, assign_zone, build_store_state,
    QUEUE_KEY_PRIORITY, OUT_DIR, KST,
)

# 집계에 쓰는 카메라(안 겹치는 2개). image는 프레임번호로 완성.
CAMERAS = [
    {  # 066 = 외부(입구·대기)
        "camera_id": "cam-066",
        "floor": "out",   # 구역 키 접미사(층 구분). 예: waiting_out
        "img_dir": Path(r"D:\223.실내외 군중 특성 데이터\01-1.정식개방데이터\Training"
                        r"\01.원천데이터\TS_2.시나리오_66.Outdoor_까페노아066(662)"),
        "img_fmt": "Outdoor_까페노아066_{n:03d}.jpg",
        "zones": Path(r"C:\Users\chicb\Downloads\Outdoor_까페노아066_001_zones.json"),
    },
    {  # 067 = 실내 1층(좌석·주문·직원)
        "camera_id": "cam-067",
        "floor": "1f",
        "img_dir": Path(r"D:\223.실내외 군중 특성 데이터\01-1.정식개방데이터\Training"
                        r"\01.원천데이터\TS_2.시나리오_67.Indoor_까페노아067(662)"),
        "img_fmt": "Indoor_까페노아067_{n:03d}.jpg",
        "zones": Path(r"C:\Users\chicb\Downloads\Indoor_까페노아067_006_zones.json"),
    },
    {  # 068 = 2층 좌석(유리 너머 촬영 → 탐지 정확도 낮음)
        "camera_id": "cam-068",
        "floor": "2f",
        "img_dir": Path(r"D:\223.실내외 군중 특성 데이터\01-1.정식개방데이터\Training"
                        r"\01.원천데이터\TS_2.시나리오_68.Indoor_까페노아068(636)"),
        "img_fmt": "Indoor_까페노아068_{n:03d}.jpg",
        "zones": Path(r"C:\Users\chicb\Downloads\Indoor_까페노아068_117_zones.json"),
    },
    {  # 071 = 2층 좌석+통로
        "camera_id": "cam-071",
        "floor": "2f",
        "img_dir": Path(r"D:\223.실내외 군중 특성 데이터\01-1.정식개방데이터\Training"
                        r"\01.원천데이터\TS_2.시나리오_71.Indoor_까페노아071(660)"),
        "img_fmt": "Indoor_까페노아071_{n:03d}.jpg",
        "zones": Path(r"C:\Users\chicb\Downloads\Indoor_까페노아071_356_zones.json"),
    },
]


def common_frame_count(cameras) -> int:
    """카메라 중 가장 적은 프레임 수 (공통으로 쓸 수 있는 범위)."""
    return min(len(list(c["img_dir"].glob("*.jpg"))) for c in cameras)


def read_image(path: Path):
    return cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)


def analyze_one(cam, frame, model, conf, iou):
    """카메라 1대 분석 → {zone_counts, in_zone}.

    zone_counts 키에는 층 접미사를 붙인다(예: seating_1f, aisle_2f).
    카메라마다 담당 층이 달라, 층별로 나눠 봐야 하기 때문.
    """
    floor = cam["floor"]
    _, zones = load_zones(cam["zones"])
    zone_counts = {f'{z["key"]}_{floor}': 0 for z in zones}
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
            zone_counts[f'{z["key"]}_{floor}'] += 1
            in_zone += 1
    return {"camera_id": cam["camera_id"], "zone_counts": zone_counts,
            "in_zone": in_zone, "image": img_path.name,
            "zones_file": cam["zones"].name}


def run_batch(start, end, model, conf, iou, store_id, interval, out_path):
    """start~end 프레임을 전부 병합해 배열 1개 파일로 저장(전송 안 함)."""
    base = datetime.now(KST)
    states = []
    for n in range(start, end + 1):
        results = [analyze_one(c, n, model, conf, iou) for c in CAMERAS]
        # 데이터셋에 촬영 시각이 없어, 프레임 간격만큼 시각을 부여(합성)
        ts = base + timedelta(seconds=interval * (n - start))
        state = merge(results, store_id, captured_at=ts)
        states.append({"frame": n, "state": state})
        if n % 50 == 0 or n == end:
            print(f"  진행 {n}/{end} ({(n-start+1)*100//(end-start+1)}%)")

    doc = {
        "note": ("병합 분석 결과. captured_at은 데이터셋에 실제 촬영 시각이 없어 "
                 f"생성 시각 기준 {interval}초 간격으로 합성한 값(실측 시각 아님)."),
        "cameras": [{"camera_id": c["camera_id"], "floor": c["floor"]} for c in CAMERAS],
        "frame_range": [start, end],
        "count": len(states),
        "states": states,
    }
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return doc


def merge(results, store_id, captured_at=None):
    """카메라별 결과 → 병합 StoreState."""
    merged: dict[str, int] = {}
    total = 0
    for r in results:
        for k, v in r["zone_counts"].items():
            merged[k] = merged.get(k, 0) + v  # 구역 안 겹침(겹치면 합)
        total += r["in_zone"]
    # 키에 층 접미사가 붙어 있으므로(waiting_out 등) 접두사로 찾아 합산한다.
    queue = 0
    for base in QUEUE_KEY_PRIORITY:
        hit = sum(v for k, v in merged.items() if k.startswith(base + "_"))
        if any(k.startswith(base + "_") for k in merged):
            queue = hit
            break
    quality = "normal" if total > 0 else "low"
    cam_id = "+".join(r["camera_id"].replace("cam-", "") for r in results)
    state = build_store_state(merged, total, queue, f"cam-{cam_id}",
                              store_id, quality, captured_at=captured_at)
    return state


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", type=int, default=6, help="양 카메라 공통 프레임 번호")
    ap.add_argument("--conf", type=float, default=0.30)
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--store-id", default="store-001")
    ap.add_argument("--post", default=None, help="API 베이스 URL (예: http://localhost:8000)")
    ap.add_argument("--all", action="store_true",
                    help="공통 프레임 전체를 배열 1개 파일로 저장(전송 안 함)")
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=None, help="기본: 공통 최대 프레임")
    ap.add_argument("--interval", type=float, default=0.5,
                    help="배치 시 프레임 간 시각 간격(초). 데이터셋이 2fps라 기본 0.5")
    args = ap.parse_args()

    # 카메라마다 프레임 수가 달라(066/067=662, 071=660, 068=636)
    # 공통으로 존재하는 범위(=가장 적은 수)로 제한한다.
    limit = common_frame_count(CAMERAS)

    if args.all:
        end = min(args.end or limit, limit)
        model = YOLO("yolo11s.pt")
        # 전체 병합 결과는 팀 공유용이라 samples/에 저장(outputs/는 gitignore 대상)
        samples_dir = Path(__file__).resolve().parents[2] / "samples"
        samples_dir.mkdir(exist_ok=True)
        out = samples_dir / "merged_all_states.json"
        print(f"=== 전체 병합 (frame {args.start}~{end}, 카메라 {len(CAMERAS)}대) ===")
        doc = run_batch(args.start, end, model, args.conf, args.iou,
                        args.store_id, args.interval, out)
        print(f"완료: {doc['count']}건 → {out}")
        return

    if not 1 <= args.frame <= limit:
        raise SystemExit(
            f"--frame {args.frame} 사용 불가. 공통 프레임 범위는 1~{limit} 입니다."
        )

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
