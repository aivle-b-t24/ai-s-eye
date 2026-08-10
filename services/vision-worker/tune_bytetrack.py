"""정해진 8개 ByteTrack 후보를 동일 구간에서 비교해 임시 권장안을 고른다."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from benchmark_tracking import (
    DEFAULT_SCENE_CUTS,
    evaluate_variant,
    load_ground_truth,
)
from cafe_tracking import (
    EXPECTED_MODEL_SHA256,
    load_scene_cuts,
    validate_model_file,
)


CANDIDATES = [
    (high, buffer, match)
    for high in (0.25, 0.35)
    for buffer in (10, 15)
    for match in (0.75, 0.80)
]


def tracker_yaml(high: float, buffer: int, match: float) -> str:
    return (
        "tracker_type: bytetrack\n"
        f"track_high_thresh: {high:.2f}\n"
        "track_low_thresh: 0.10\n"
        f"new_track_thresh: {high:.2f}\n"
        f"track_buffer: {buffer}\n"
        f"match_thresh: {match:.2f}\n"
        "fuse_score: true\n"
    )


def candidate_score(results: list[dict]) -> tuple[float, float, float]:
    matches = sum(result["tracking_proxy"]["normal_matches"] for result in results)
    breaks = sum(result["tracking_proxy"]["id_breaks"] for result in results)
    break_rate = breaks / max(matches, 1)
    mean_recall = sum(result["detection"]["recall_iou50"] for result in results) / len(results)
    mean_count_mae = sum(result["detection"]["count_mae"] for result in results) / len(results)
    return break_rate, -mean_recall, mean_count_mae


def main() -> None:
    parser = argparse.ArgumentParser(description="CAFE ByteTrack 8개 설정 비교")
    parser.add_argument("--cafe-root", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--gt-zip", type=Path, required=True)
    parser.add_argument("--cameras", nargs="+", default=["5", "21"])
    parser.add_argument("--limit", type=int, default=55)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "outputs" / "benchmarks" / "bytetrack_tuning.json",
    )
    args = parser.parse_args()

    model_sha = validate_model_file(args.model, EXPECTED_MODEL_SHA256)
    cuts = load_scene_cuts(DEFAULT_SCENE_CUTS)
    ground_truth = load_ground_truth(args.gt_zip, {int(camera) for camera in args.cameras})
    candidates = []
    with tempfile.TemporaryDirectory(prefix="aiseye-bytetrack-") as temp_dir:
        for high, buffer, match in CANDIDATES:
            name = f"h{int(high * 100)}-b{buffer}-m{int(match * 100)}"
            tracker_path = Path(temp_dir) / f"{name}.yaml"
            tracker_path.write_text(tracker_yaml(high, buffer, match), encoding="utf-8")
            results = [
                evaluate_variant(
                    name=name,
                    cafe_root=args.cafe_root,
                    model_path=args.model,
                    clip=str(camera),
                    cuts=cuts.get(str(camera), set()),
                    ground_truth=ground_truth,
                    improved=True,
                    improved_tracker=tracker_path,
                    segment_limit=args.limit,
                )
                for camera in args.cameras
            ]
            score = candidate_score(results)
            candidates.append({
                "name": name,
                "config": {"high_new": high, "buffer": buffer, "match": match},
                "weighted_id_break_rate": round(score[0], 6),
                "mean_recall_iou50": round(-score[1], 6),
                "mean_count_mae": round(score[2], 6),
                "results": results,
            })

    candidates.sort(
        key=lambda candidate: (
            candidate["weighted_id_break_rate"],
            -candidate["mean_recall_iou50"],
            candidate["mean_count_mae"],
        )
    )
    report = {
        "schema_version": "1.0",
        "model_sha256": model_sha,
        "selection_status": "provisional_proxy; requires manual MOT labels for IDF1/HOTA",
        "selected": candidates[0]["name"],
        "candidates": candidates,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        "selected": report["selected"],
        "ranking": [
            {
                "name": candidate["name"],
                "id_break_rate": candidate["weighted_id_break_rate"],
                "recall": candidate["mean_recall_iou50"],
                "count_mae": candidate["mean_count_mae"],
            }
            for candidate in candidates
        ],
    }, indent=2))
    print(f"report: {args.output}")


if __name__ == "__main__":
    main()
