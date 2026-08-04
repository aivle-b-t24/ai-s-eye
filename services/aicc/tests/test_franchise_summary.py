from typing import Any

from aicc.franchise_summary import summarize_scenario


def scenario() -> dict[str, Any]:
    return {
        "stores": [
            {"store_id": "store-001", "store_name": "동명점"},
            {"store_id": "store-002", "store_name": "수완점"},
        ],
        "states": [
            {
                "store_id": "store-001",
                "captured_at": "2026-07-22T10:00:00+09:00",
                "visible_person_count": 8,
                "queue_count_estimate": 1,
                "zone_counts": {"counter": 2, "waiting": 1, "seating": 5},
                "quality_status": "normal",
            },
            {
                "store_id": "store-001",
                "captured_at": "2026-07-22T12:00:00+09:00",
                "visible_person_count": 28,
                "queue_count_estimate": 9,
                "zone_counts": {"counter": 7, "waiting": 9, "seating": 12},
                "quality_status": "normal",
            },
            {
                "store_id": "store-002",
                "captured_at": "2026-07-22T10:00:00+09:00",
                "visible_person_count": 10,
                "queue_count_estimate": 0,
                "zone_counts": {"counter": 2, "waiting": 0, "seating": 8},
                "quality_status": "stale",
            },
        ],
        "orders": [
            {
                "store_id": "store-001",
                "status": "received",
                "items": [{"menu_id": "menu-001", "name": "아메리카노", "quantity": 2}],
            },
            {
                "store_id": "store-001",
                "status": "preparing",
                "items": [{"menu_id": "menu-001", "name": "아메리카노", "quantity": 3}],
            },
            {
                "store_id": "store-002",
                "status": "completed",
                "items": [{"menu_id": "menu-021", "name": "크루아상", "quantity": 2}],
            },
        ],
    }


def by_id(summaries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {s["store_id"]: s for s in summaries}


def test_one_summary_per_store() -> None:
    summaries = summarize_scenario(scenario())
    assert [s["store_id"] for s in summaries] == ["store-001", "store-002"]


def test_peak_and_average_person_count() -> None:
    s = by_id(summarize_scenario(scenario()))["store-001"]
    assert s["peak_person_count"] == 28
    assert s["peak_queue_count"] == 9
    assert s["avg_person_count"] == 18.0  # (8+28)/2


def test_abnormal_video_flag() -> None:
    summaries = by_id(summarize_scenario(scenario()))
    assert summaries["store-001"]["abnormal_video"] is False
    assert summaries["store-002"]["abnormal_video"] is True  # stale 있음


def test_needs_counter_attention_flag() -> None:
    sc = scenario()
    # 대기 있는데 카운터 0명인 상태 추가
    sc["states"].append(
        {
            "store_id": "store-001",
            "captured_at": "2026-07-22T13:00:00+09:00",
            "visible_person_count": 15,
            "queue_count_estimate": 9,
            "zone_counts": {"counter": 0, "waiting": 9, "seating": 6},
            "quality_status": "normal",
        }
    )
    s = by_id(summarize_scenario(sc))["store-001"]
    assert s["needs_counter_attention"] is True


def test_order_counts_and_status() -> None:
    s = by_id(summarize_scenario(scenario()))["store-001"]
    assert s["order_count"] == 2
    assert s["order_status_counts"] == {"received": 1, "preparing": 1}


def test_top_menus_by_quantity() -> None:
    s = by_id(summarize_scenario(scenario()))["store-001"]
    assert s["top_menus"][0] == "menu-001"  # 총 5개로 최다


def test_handles_empty_scenario() -> None:
    assert summarize_scenario({}) == []


def test_handles_store_with_no_states_or_orders() -> None:
    sc = {"stores": [{"store_id": "store-003", "store_name": "빈점"}], "states": [], "orders": []}
    s = summarize_scenario(sc)[0]
    assert s["state_count"] == 0
    assert s["order_count"] == 0
    assert s["peak_person_count"] == 0
