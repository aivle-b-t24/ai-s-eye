"""주문 이벤트로부터 '동시 대기 주문 수'(대기열 길이)를 재구성한다.

주문 하나는 상태 이벤트(received -> preparing -> ready -> completed)로 흩어져
저장된다. 각 주문의 '대기 구간'은 접수(received)부터 종료(completed/cancelled/
rejected)까지로 보고, 어떤 시각 t에 그 구간에 걸친 주문을 세면 그 순간의 대기
주문 수가 된다. 이는 예측이 아니라 로그가 함의하는 현재 대기열의 집계다.

정직성: 이벤트 시각 자체는 정확하지만, 데이터가 합성이면 값은 실측 혼잡이 아니라
생성기 재현이다(실 POS 연동 시 동일 코드로 실측 대기열 산출). 또한 '대기 주문 수'는
'대기 인원'과 1:1이 아닐 수 있다(단체 주문 1건 = 여러 명).
"""

from datetime import datetime, timezone

from .models import OrderEvent, OrderStatus


# 주문의 '대기 구간'을 끝내는(손님이 떠나는) 상태들
_TERMINAL_STATUSES = {
    OrderStatus.COMPLETED,
    OrderStatus.CANCELLED,
    OrderStatus.REJECTED,
}

# (start, end) 구간. end=None 이면 관측 창 안에서 종료가 확인되지 않은 열린 주문.
WaitingInterval = tuple[datetime, datetime | None]


def build_waiting_intervals(orders: list[OrderEvent]) -> list[WaitingInterval]:
    """주문 이벤트를 order_id로 묶어 각 주문의 대기 구간을 복원한다.

    - 시작 = ``received`` 이벤트 시각(없으면 그 주문의 가장 이른 이벤트 시각).
    - 종료 = 가장 이른 종료 상태(completed/cancelled/rejected) 시각(없으면 None).
    구간이 성립하지 않는(이벤트가 하나도 없는) 주문은 제외된다.
    """
    events_by_order: dict[str, list[OrderEvent]] = {}
    for event in orders:
        events_by_order.setdefault(event.order_id, []).append(event)

    intervals: list[WaitingInterval] = []
    for events in events_by_order.values():
        ordered = sorted(events, key=lambda item: (_utc(item.occurred_at), item.event_id))
        received = next(
            (event for event in ordered if event.status == OrderStatus.RECEIVED),
            None,
        )
        start = _utc(received.occurred_at) if received else _utc(ordered[0].occurred_at)
        terminal = next(
            (event for event in ordered if event.status in _TERMINAL_STATUSES),
            None,
        )
        end = _utc(terminal.occurred_at) if terminal else None
        if end is not None and end < start:
            # 시각 역전(데이터 오류)은 순간 대기로 축소해 무시한다.
            end = start
        intervals.append((start, end))
    return intervals


def concurrency_at(intervals: list[WaitingInterval], instant: datetime) -> int:
    """주어진 순간에 진행 중(대기 구간에 걸친) 주문 수.

    구간은 반열린 ``[start, end)``: 시작 시각은 포함, 종료 시각은 제외한다.
    열린 주문(end=None)은 그 순간 여전히 대기 중으로 본다. 라이브 화면의
    '지금 대기 인원'처럼 특정 프레임 시각에 맞춘 값을 낼 때 쓴다.
    """
    moment = _utc(instant)
    count = 0
    for start, end in intervals:
        if start <= moment and (end is None or moment < end):
            count += 1
    return count


def average_concurrency(
    intervals: list[WaitingInterval],
    start_at: datetime,
    end_at: datetime,
) -> float:
    """구간 [start_at, end_at) 동안의 시간가중 평균 동시 대기 주문 수.

    각 주문이 창 안에 걸친 시간의 합 / 창 길이. 창을 벗어난 부분은 잘라낸다(clip).
    열린 주문(end=None)은 창 끝까지 대기 중으로 본다.
    """
    win_start = _utc(start_at)
    win_end = _utc(end_at)
    window_seconds = (win_end - win_start).total_seconds()
    if window_seconds <= 0:
        return 0.0

    active_seconds = 0.0
    for raw_start, raw_end in intervals:
        seg_start = max(raw_start, win_start)
        seg_end = min(raw_end if raw_end is not None else win_end, win_end)
        overlap = (seg_end - seg_start).total_seconds()
        if overlap > 0:
            active_seconds += overlap
    return round(active_seconds / window_seconds, 2)


def peak_concurrency(
    intervals: list[WaitingInterval],
    start_at: datetime,
    end_at: datetime,
) -> int:
    """구간 [start_at, end_at) 안에서 순간 동시 대기 주문 수의 최댓값(sweep line)."""
    win_start = _utc(start_at)
    win_end = _utc(end_at)
    if (win_end - win_start).total_seconds() <= 0:
        return 0

    # 창에 걸치는 구간의 진입(+1)/이탈(-1) 시점. 이탈이 같은 시각이면 먼저 처리해
    # '닿기만 하고 지나간' 구간이 겹침으로 잡히지 않게 한다(반열린 구간 [s, e)).
    deltas: list[tuple[datetime, int]] = []
    for raw_start, raw_end in intervals:
        seg_start = max(raw_start, win_start)
        seg_end = min(raw_end if raw_end is not None else win_end, win_end)
        if seg_end <= seg_start:
            continue
        deltas.append((seg_start, 1))
        deltas.append((seg_end, -1))

    deltas.sort(key=lambda item: (item[0], item[1]))
    running = 0
    peak = 0
    for _, change in deltas:
        running += change
        peak = max(peak, running)
    return peak


def _utc(value: datetime) -> datetime:
    """비교·연산을 위해 UTC로 정규화한다(naive는 UTC로 간주)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
