from typing import Any

import pytest

from aicc.franchise_validation import (
    VALID_ORDER_STATUS,
    VALID_QUALITY_STATUS,
    validate_scenario,
)


def valid_menus() -> dict[str, Any]:
    return {
        "data_source": "mock",
        "menus": [
            {"store_id": "store-001", "menu_id": "menu-001", "name": "아메리카노"},
            {"store_id": "store-001", "menu_id": "menu-003", "name": "카푸치노"},
            {"store_id": "store-002", "menu_id": "menu-001", "name": "아메리카노"},
            {"store_id": "store-002", "menu_id": "menu-021", "name": "크루아상"},
        ],
    }


def valid_scenario() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
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
        ],
        "orders": [
            {
                "event_id": "event-001",
                "order_id": "order-001",
                "store_id": "store-001",
                "occurred_at": "2026-07-22T10:31:00+09:00",
                "status": "received",
                "items": [{"menu_id": "menu-001", "name": "아메리카노", "quantity": 2}],
            },
            {
                "event_id": "event-004",
                "order_id": "order-001",
                "store_id": "store-002",
                "occurred_at": "2026-07-22T10:35:00+09:00",
                "status": "received",
                "items": [{"menu_id": "menu-021", "name": "크루아상", "quantity": 1}],
            },
        ],
        "expected_insights": [
            {"store_id": "store-002", "evidence": {"popular_menu_ids": ["menu-021"]}},
        ],
    }


# --- 통과: 올바른 데이터는 문제 0개 ---


def test_valid_data_has_no_errors() -> None:
    assert validate_scenario(valid_scenario(), valid_menus()) == []


# --- 각 검사가 실제로 문제를 잡아내는가 ---


def test_detects_invalid_order_status() -> None:
    sc = valid_scenario()
    sc["orders"][0]["status"] = "delayed"
    errors = validate_scenario(sc, valid_menus())
    assert any("status" in e for e in errors)


def test_detects_menu_name_mismatch() -> None:
    sc = valid_scenario()
    sc["orders"][0]["items"][0]["name"] = "바닐라라떼"  # menu-001은 아메리카노
    errors = validate_scenario(sc, valid_menus())
    assert any("이름 불일치" in e for e in errors)


def test_detects_unknown_menu_id() -> None:
    sc = valid_scenario()
    sc["orders"][0]["items"][0]["menu_id"] = "menu-999"
    errors = validate_scenario(sc, valid_menus())
    assert any("menu-999" in e for e in errors)


def test_detects_invalid_quality_status() -> None:
    sc = valid_scenario()
    sc["states"][0]["quality_status"] = "broken"
    errors = validate_scenario(sc, valid_menus())
    assert any("quality_status" in e for e in errors)


def test_detects_out_of_order_times() -> None:
    sc = valid_scenario()
    sc["states"][0]["captured_at"] = "2026-07-22T13:00:00+09:00"  # 뒤 항목보다 늦음
    errors = validate_scenario(sc, valid_menus())
    assert any("순서" in e for e in errors)


def test_detects_same_menu_id_different_product() -> None:
    menus = valid_menus()
    menus["menus"].append(
        {"store_id": "store-002", "menu_id": "menu-003", "name": "소금빵"}  # store-001은 카푸치노
    )
    errors = validate_scenario(valid_scenario(), menus)
    assert any("다른 상품" in e for e in errors)


def test_detects_insight_menu_not_in_store() -> None:
    sc = valid_scenario()
    sc["expected_insights"][0]["evidence"]["popular_menu_ids"] = ["menu-017"]
    errors = validate_scenario(sc, valid_menus())
    assert any("menu-017" in e for e in errors)


def test_detects_missing_store_id_in_state() -> None:
    sc = valid_scenario()
    del sc["states"][0]["store_id"]
    errors = validate_scenario(sc, valid_menus())
    assert any("store_id" in e for e in errors)


# --- 유효값 전부 통과하는가 (허용된 값은 오류가 아니어야) ---


@pytest.mark.parametrize("status", sorted(VALID_ORDER_STATUS))
def test_all_valid_order_statuses_pass(status: str) -> None:
    sc = valid_scenario()
    sc["orders"][0]["status"] = status
    assert validate_scenario(sc, valid_menus()) == []


@pytest.mark.parametrize("quality", sorted(VALID_QUALITY_STATUS))
def test_all_valid_quality_statuses_pass(quality: str) -> None:
    sc = valid_scenario()
    for st in sc["states"]:
        st["quality_status"] = quality
    assert validate_scenario(sc, valid_menus()) == []


# --- 경계 상황: 목록이 없거나 비었을 때 ---


def test_missing_stores_reported() -> None:
    sc = valid_scenario()
    del sc["stores"]
    errors = validate_scenario(sc, valid_menus())
    assert any("stores" in e for e in errors)


def test_empty_stores_reported() -> None:
    sc = valid_scenario()
    sc["stores"] = []
    errors = validate_scenario(sc, valid_menus())
    assert any("stores" in e for e in errors)


def test_missing_states_reported() -> None:
    sc = valid_scenario()
    del sc["states"]
    errors = validate_scenario(sc, valid_menus())
    assert any("states" in e for e in errors)


def test_missing_orders_reported() -> None:
    sc = valid_scenario()
    del sc["orders"]
    errors = validate_scenario(sc, valid_menus())
    assert any("orders" in e for e in errors)


def test_empty_order_items_reported() -> None:
    sc = valid_scenario()
    sc["orders"][0]["items"] = []
    errors = validate_scenario(sc, valid_menus())
    assert any("items" in e for e in errors)


# --- 형식이 깨졌을 때 (예외로 죽지 않고 오류 목록으로 돌려주는가) ---


def test_non_dict_scenario_reported() -> None:
    errors = validate_scenario("망가진 데이터", valid_menus())
    assert errors  # 예외 없이 문제 목록을 돌려줘야 한다


def test_malformed_captured_at_reported() -> None:
    sc = valid_scenario()
    sc["states"][0]["captured_at"] = "2026/07/22 10시"
    errors = validate_scenario(sc, valid_menus())
    assert any("captured_at" in e for e in errors)


def test_negative_count_reported() -> None:
    sc = valid_scenario()
    sc["states"][0]["visible_person_count"] = -3
    errors = validate_scenario(sc, valid_menus())
    assert any("visible_person_count" in e for e in errors)


def test_missing_store_name_reported() -> None:
    sc = valid_scenario()
    del sc["stores"][0]["store_name"]
    errors = validate_scenario(sc, valid_menus())
    assert any("store_name" in e for e in errors)


def test_state_store_id_not_in_stores_reported() -> None:
    sc = valid_scenario()
    sc["states"][0]["store_id"] = "store-999"
    errors = validate_scenario(sc, valid_menus())
    assert any("store-999" in e for e in errors)


# --- 세부 동작 ---


def test_time_order_is_checked_per_store() -> None:
    """한 매장 순서가 틀려도 다른 매장은 영향받지 않는다."""
    sc = valid_scenario()
    sc["states"].append(
        {
            "store_id": "store-002",
            "captured_at": "2026-07-22T09:00:00+09:00",
            "visible_person_count": 5,
            "queue_count_estimate": 0,
            "zone_counts": {"counter": 1, "waiting": 0, "seating": 4},
            "quality_status": "normal",
        }
    )
    sc["states"].append(
        {
            "store_id": "store-002",
            "captured_at": "2026-07-22T08:00:00+09:00",
            "visible_person_count": 5,
            "queue_count_estimate": 0,
            "zone_counts": {"counter": 1, "waiting": 0, "seating": 4},
            "quality_status": "normal",
        }
    )
    errors = validate_scenario(sc, valid_menus())
    assert any("store-002" in e and "순서" in e for e in errors)
    assert not any("store-001" in e and "순서" in e for e in errors)


def test_popular_menu_ids_at_top_level_also_checked() -> None:
    """popular_menu_ids가 evidence 밖(최상위)에 있어도 검사한다."""
    sc = valid_scenario()
    sc["expected_insights"] = [{"store_id": "store-002", "popular_menu_ids": ["menu-999"]}]
    errors = validate_scenario(sc, valid_menus())
    assert any("menu-999" in e for e in errors)


def test_detects_out_of_order_order_times() -> None:
    """매장별 주문이 시각 순서가 아니면 잡는다."""
    sc = valid_scenario()
    # store-001 주문 2건을 시각 역순으로
    sc["orders"][0]["occurred_at"] = "2026-07-22T13:00:00+09:00"
    sc["orders"].append(
        {
            "event_id": "event-002",
            "order_id": "order-002",
            "store_id": "store-001",
            "occurred_at": "2026-07-22T11:00:00+09:00",
            "status": "received",
            "items": [{"menu_id": "menu-001", "name": "아메리카노", "quantity": 1}],
        }
    )
    errors = validate_scenario(sc, valid_menus())
    assert any("orders" in e and "순서" in e for e in errors)


def test_detects_malformed_order_time() -> None:
    sc = valid_scenario()
    sc["orders"][0]["occurred_at"] = "10시 31분"
    errors = validate_scenario(sc, valid_menus())
    assert any("occurred_at" in e for e in errors)


def test_order_time_order_is_per_store() -> None:
    """한 매장 주문 순서가 틀려도 다른 매장은 영향 없다."""
    sc = valid_scenario()
    sc["orders"][0]["occurred_at"] = "2026-07-22T13:00:00+09:00"
    sc["orders"].append(
        {
            "event_id": "event-002",
            "order_id": "order-002",
            "store_id": "store-001",
            "occurred_at": "2026-07-22T11:00:00+09:00",
            "status": "received",
            "items": [{"menu_id": "menu-001", "name": "아메리카노", "quantity": 1}],
        }
    )
    errors = validate_scenario(sc, valid_menus())
    assert any("store-001" in e and "orders" in e and "순서" in e for e in errors)
    assert not any("store-002" in e and "orders" in e and "순서" in e for e in errors)


def test_multiple_errors_returned_together() -> None:
    """오류가 여러 개면 첫 번째에서 멈추지 않고 모두 돌려준다."""
    sc = valid_scenario()
    sc["orders"][0]["status"] = "delayed"
    sc["states"][0]["quality_status"] = "broken"
    sc["states"][0]["visible_person_count"] = -1
    errors = validate_scenario(sc, valid_menus())
    assert len(errors) >= 3
