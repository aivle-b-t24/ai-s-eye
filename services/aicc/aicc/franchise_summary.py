"""프랜차이즈 샘플 → 매장별 요약 변환기.

이슈 #41: 샘플을 읽어 '매장별 요약 입력'으로 변환되는지 확인한다.
슈퍼바이저 질문(예: "어느 매장이 붐볐어?")에 답하는 Analytics Tool이
이 요약을 근거로 삼는다. 여기서는 원본 상태·주문 샘플을 매장 단위로 접어
핵심 지표만 추린다.
"""

from collections import Counter
from typing import Any


def summarize_scenario(scenario: Any) -> list[dict[str, Any]]:
    """시나리오 샘플을 매장별 요약 목록으로 바꾼다.

    각 요약은 한 매장의 시간대 지표(피크 인원·대기, 영상 이상 여부,
    카운터 공백 여부)와 주문 지표(건수·상태 분포·인기 메뉴)를 담는다.
    """
    stores = scenario.get("stores") if isinstance(scenario, dict) else None
    states = scenario.get("states") if isinstance(scenario, dict) else None
    orders = scenario.get("orders") if isinstance(scenario, dict) else None
    stores = stores if isinstance(stores, list) else []
    states = states if isinstance(states, list) else []
    orders = orders if isinstance(orders, list) else []

    name_by_id = {
        s["store_id"]: s.get("store_name")
        for s in stores
        if isinstance(s, dict) and "store_id" in s
    }

    # 매장 등장 순서 유지
    order_keys: list[str] = []
    for s in stores:
        if isinstance(s, dict) and s.get("store_id") not in order_keys:
            order_keys.append(s["store_id"])

    summaries: list[dict[str, Any]] = []
    for sid in order_keys:
        s_states = [st for st in states if isinstance(st, dict) and st.get("store_id") == sid]
        s_orders = [o for o in orders if isinstance(o, dict) and o.get("store_id") == sid]

        persons = [st.get("visible_person_count", 0) for st in s_states]
        queues = [st.get("queue_count_estimate", 0) for st in s_states]

        abnormal_video = any(st.get("quality_status") != "normal" for st in s_states)
        needs_counter = any(
            (st.get("zone_counts") or {}).get("counter", 0) == 0
            and st.get("queue_count_estimate", 0) > 0
            for st in s_states
        )

        menu_qty: Counter = Counter()
        status_counts: Counter = Counter()
        for o in s_orders:
            status_counts[o.get("status")] += 1
            for it in o.get("items") or []:
                if isinstance(it, dict) and it.get("menu_id"):
                    menu_qty[it["menu_id"]] += it.get("quantity", 0)

        summaries.append(
            {
                "store_id": sid,
                "store_name": name_by_id.get(sid),
                "state_count": len(s_states),
                "peak_person_count": max(persons) if persons else 0,
                "peak_queue_count": max(queues) if queues else 0,
                "avg_person_count": round(sum(persons) / len(persons), 1) if persons else 0,
                "abnormal_video": abnormal_video,
                "needs_counter_attention": needs_counter,
                "order_count": len(s_orders),
                "order_status_counts": dict(status_counts),
                "top_menus": [mid for mid, _ in menu_qty.most_common(3)],
            }
        )

    return summaries
