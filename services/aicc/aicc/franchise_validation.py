"""프랜차이즈 샘플 데이터(scenario + menus) 검증기.

이슈 #41: 두 매장 운영 샘플이 대시보드·AI 분석에서 안전하게 쓰이도록,
문서·JSON·분석 코드가 같은 값을 쓰는지 확인한다.

핵심 함수는 validate_scenario(scenario, menus)로, 문제를 문자열 목록으로 돌려준다.
목록이 비어 있으면 통과다. 예외를 던지지 않으므로 호출한 쪽에서 개수를 보고 판단한다.
"""

from datetime import datetime
from typing import Any


VALID_QUALITY_STATUS = {"normal", "low", "stale", "unknown"}
VALID_ORDER_STATUS = {
    "received",
    "preparing",
    "ready",
    "completed",
    "cancelled",
    "rejected",
}


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _menu_lookup(menus: Any) -> dict[tuple[str, str], str]:
    """(store_id, menu_id) -> 메뉴 이름 표를 만든다."""
    table: dict[tuple[str, str], str] = {}
    items = menus.get("menus") if isinstance(menus, dict) else None
    if isinstance(items, list):
        for m in items:
            if isinstance(m, dict) and "store_id" in m and "menu_id" in m:
                table[(m["store_id"], m["menu_id"])] = m.get("name")
    return table


def validate_scenario(scenario: Any, menus: Any) -> list[str]:
    """시나리오 샘플과 메뉴 샘플을 대조해 문제 목록을 돌려준다."""
    errors: list[str] = []

    if not isinstance(scenario, dict):
        return ["scenario 최상위가 객체(JSON object)가 아니다."]
    if not isinstance(menus, dict):
        errors.append("menus 최상위가 객체(JSON object)가 아니다.")

    # 1) 매장 목록 확인 + 유효한 store_id 수집
    stores = scenario.get("stores")
    store_ids: set[str] = set()
    if not isinstance(stores, list) or not stores:
        errors.append("stores 목록이 없거나 비어 있다.")
    else:
        for i, s in enumerate(stores):
            if not isinstance(s, dict) or "store_id" not in s:
                errors.append(f"stores[{i}]에 store_id가 없다.")
                continue
            store_ids.add(s["store_id"])
            if not s.get("store_name"):
                errors.append(f"store {s['store_id']}에 store_name이 없다.")

    menu_table = _menu_lookup(menus)
    menu_ids_by_store: dict[str, set[str]] = {}
    for (sid, mid) in menu_table:
        menu_ids_by_store.setdefault(sid, set()).add(mid)

    # 2) 상태(states) 확인
    states = scenario.get("states")
    times_by_store: dict[str, list[datetime]] = {}
    if not isinstance(states, list):
        errors.append("states 목록이 없다.")
    else:
        for i, st in enumerate(states):
            if not isinstance(st, dict):
                errors.append(f"states[{i}]가 객체가 아니다.")
                continue
            sid = st.get("store_id")
            if not sid:
                errors.append(f"states[{i}]에 store_id가 없다.")
            elif store_ids and sid not in store_ids:
                errors.append(f"states[{i}]의 store_id '{sid}'가 stores에 없다.")
            q = st.get("quality_status")
            if q not in VALID_QUALITY_STATUS:
                errors.append(
                    f"states[{i}] quality_status '{q}'는 허용값이 아니다 "
                    f"({', '.join(sorted(VALID_QUALITY_STATUS))})."
                )
            for field in ("visible_person_count", "queue_count_estimate"):
                v = st.get(field)
                if not isinstance(v, int) or v < 0:
                    errors.append(f"states[{i}] {field}는 0 이상의 정수여야 한다 (현재 {v!r}).")
            t = _parse_time(st.get("captured_at"))
            if t is None:
                errors.append(f"states[{i}] captured_at 시각 형식이 잘못됐다.")
            elif sid:
                times_by_store.setdefault(sid, []).append(t)

    # 3) 매장별 상태 시각이 순서대로인가
    for sid, times in times_by_store.items():
        if times != sorted(times):
            errors.append(f"store {sid}의 states 시각이 순서대로가 아니다.")

    # 4) 주문(orders) 확인 + 메뉴 대조
    orders = scenario.get("orders")
    order_times_by_store: dict[str, list[datetime]] = {}
    if not isinstance(orders, list):
        errors.append("orders 목록이 없다.")
    else:
        for o in orders:
            if not isinstance(o, dict):
                errors.append("orders 항목이 객체가 아니다.")
                continue
            tag = o.get("event_id") or o.get("order_id") or "?"
            sid = o.get("store_id")
            if not sid:
                errors.append(f"주문 {tag}에 store_id가 없다.")
            if o.get("status") not in VALID_ORDER_STATUS:
                errors.append(
                    f"주문 {tag} status '{o.get('status')}'는 허용값이 아니다 "
                    f"({', '.join(sorted(VALID_ORDER_STATUS))})."
                )
            ot = _parse_time(o.get("occurred_at"))
            if o.get("occurred_at") is not None and ot is None:
                errors.append(f"주문 {tag} occurred_at 시각 형식이 잘못됐다.")
            elif ot is not None and sid:
                order_times_by_store.setdefault(sid, []).append(ot)
            items = o.get("items")
            if not isinstance(items, list) or not items:
                errors.append(f"주문 {tag}에 items가 없다.")
                continue
            for it in items:
                if not isinstance(it, dict):
                    errors.append(f"주문 {tag}의 item이 객체가 아니다.")
                    continue
                mid = it.get("menu_id")
                real = menu_table.get((sid, mid))
                if real is None:
                    errors.append(f"주문 {tag}의 {mid}는 {sid} 메뉴에 없다.")
                elif real != it.get("name"):
                    errors.append(
                        f"주문 {tag}의 {mid} 이름 불일치: 주문 '{it.get('name')}' vs 메뉴 '{real}'."
                    )

    # 4-1) 매장별 주문이 시각(occurred_at) 순서대로인가
    for sid, times in order_times_by_store.items():
        if times != sorted(times):
            errors.append(f"store {sid}의 orders 시각이 순서대로가 아니다.")

    # 5) 같은 menu_id가 매장마다 다른 상품이면 지점 비교가 왜곡된다
    names_by_id: dict[str, set[str]] = {}
    for (sid, mid), name in menu_table.items():
        names_by_id.setdefault(mid, set()).add(name)
    for mid, names in sorted(names_by_id.items()):
        if len(names) > 1:
            errors.append(f"menu_id {mid}가 매장마다 다른 상품이다: {sorted(names)}.")

    # 6) 분석(expected_insights)이 가리키는 메뉴가 그 매장에 실제 있나
    insights = scenario.get("expected_insights")
    if isinstance(insights, list):
        for ins in insights:
            if not isinstance(ins, dict):
                continue
            sid = ins.get("store_id")
            evidence = ins.get("evidence")
            popular = []
            if isinstance(evidence, dict):
                popular = evidence.get("popular_menu_ids") or []
            popular = popular or ins.get("popular_menu_ids") or []
            for mid in popular:
                if mid not in menu_ids_by_store.get(sid, set()):
                    errors.append(f"insight({sid})의 {mid}가 {sid} 메뉴에 없다.")

    return errors
