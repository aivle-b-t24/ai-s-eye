from datetime import datetime, timedelta, timezone

from app.models import OrderEvent, OrderItem, OrderStatus
from app.order_queue import (
    average_concurrency,
    build_waiting_intervals,
    concurrency_at,
    peak_concurrency,
)


def _order(order_id: str, occurred_at: datetime, status: OrderStatus) -> OrderEvent:
    return OrderEvent(
        event_id=f"{order_id}-{status.value}",
        order_id=order_id,
        store_id="store-001",
        occurred_at=occurred_at,
        status=status,
        items=[OrderItem(menu_id="menu-001", name="아메리카노", quantity=1)],
    )


BASE = datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc)


def _at(minutes: int) -> datetime:
    return BASE + timedelta(minutes=minutes)


def test_interval_uses_received_start_and_earliest_terminal_end() -> None:
    orders = [
        _order("a", _at(0), OrderStatus.RECEIVED),
        _order("a", _at(5), OrderStatus.PREPARING),
        _order("a", _at(30), OrderStatus.COMPLETED),
    ]
    intervals = build_waiting_intervals(orders)
    assert intervals == [(_at(0), _at(30))]


def test_interval_open_when_no_terminal_event() -> None:
    orders = [
        _order("a", _at(0), OrderStatus.RECEIVED),
        _order("a", _at(10), OrderStatus.READY),
    ]
    (start, end), = build_waiting_intervals(orders)
    assert start == _at(0)
    assert end is None


def test_average_concurrency_is_time_weighted() -> None:
    # A: 10:00~10:30, B: 10:15~10:45 → 각 30분씩, 창 60분 → (1800+1800)/3600 = 1.0
    orders = [
        _order("a", _at(0), OrderStatus.RECEIVED),
        _order("a", _at(30), OrderStatus.COMPLETED),
        _order("b", _at(15), OrderStatus.RECEIVED),
        _order("b", _at(45), OrderStatus.COMPLETED),
    ]
    intervals = build_waiting_intervals(orders)
    assert average_concurrency(intervals, _at(0), _at(60)) == 1.0


def test_open_order_counts_until_window_end() -> None:
    # 열린 주문(종료 없음)은 창 끝까지 대기로 본다: 10:50~11:00 = 600s / 3600 = 0.17
    orders = [_order("c", _at(50), OrderStatus.RECEIVED)]
    intervals = build_waiting_intervals(orders)
    assert average_concurrency(intervals, _at(0), _at(60)) == 0.17


def test_peak_concurrency_counts_overlap() -> None:
    orders = [
        _order("a", _at(0), OrderStatus.RECEIVED),
        _order("a", _at(30), OrderStatus.COMPLETED),
        _order("b", _at(15), OrderStatus.RECEIVED),
        _order("b", _at(45), OrderStatus.COMPLETED),
    ]
    intervals = build_waiting_intervals(orders)
    assert peak_concurrency(intervals, _at(0), _at(60)) == 2


def test_peak_treats_intervals_as_half_open() -> None:
    # A가 끝나는 순간 D가 시작 → 동시 대기로 겹치지 않아야 한다(반열린 구간).
    orders = [
        _order("a", _at(0), OrderStatus.RECEIVED),
        _order("a", _at(30), OrderStatus.COMPLETED),
        _order("d", _at(30), OrderStatus.RECEIVED),
        _order("d", _at(45), OrderStatus.COMPLETED),
    ]
    intervals = build_waiting_intervals(orders)
    assert peak_concurrency(intervals, _at(0), _at(60)) == 1


def test_concurrency_at_counts_in_flight_orders() -> None:
    # A: 10:00~10:30, B: 10:15~10:45. 10:20엔 둘 다 진행 중 → 2.
    orders = [
        _order("a", _at(0), OrderStatus.RECEIVED),
        _order("a", _at(30), OrderStatus.COMPLETED),
        _order("b", _at(15), OrderStatus.RECEIVED),
        _order("b", _at(45), OrderStatus.COMPLETED),
    ]
    intervals = build_waiting_intervals(orders)
    assert concurrency_at(intervals, _at(20)) == 2
    assert concurrency_at(intervals, _at(40)) == 1   # A 종료, B만
    assert concurrency_at(intervals, _at(50)) == 0   # 둘 다 종료


def test_concurrency_at_is_half_open_at_end() -> None:
    # 종료 시각은 제외(반열린 구간): 10:30에 A는 이미 대기 아님.
    orders = [
        _order("a", _at(0), OrderStatus.RECEIVED),
        _order("a", _at(30), OrderStatus.COMPLETED),
    ]
    intervals = build_waiting_intervals(orders)
    assert concurrency_at(intervals, _at(0)) == 1    # 시작 시각은 포함
    assert concurrency_at(intervals, _at(30)) == 0   # 종료 시각은 제외


def test_window_clips_orders_crossing_boundaries() -> None:
    # 창(10:10~10:40) 밖으로 걸친 주문은 겹친 부분만 계산: 10:10~10:40 = 30분 전부
    orders = [
        _order("a", _at(0), OrderStatus.RECEIVED),
        _order("a", _at(60), OrderStatus.COMPLETED),
    ]
    intervals = build_waiting_intervals(orders)
    assert average_concurrency(intervals, _at(10), _at(40)) == 1.0
    assert peak_concurrency(intervals, _at(10), _at(40)) == 1
