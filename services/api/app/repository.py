from threading import RLock

from .models import OrderEvent, StoreState


class InMemoryRepository:
    """Temporary repository used until the team agrees on the DB schema."""

    def __init__(self) -> None:
        self._store_states: dict[str, StoreState] = {}
        self._order_events: dict[str, OrderEvent] = {}
        self._lock = RLock()

    def save_store_state(self, state: StoreState) -> StoreState:
        with self._lock:
            self._store_states[state.store_id] = state
        return state

    def get_store_state(self, store_id: str) -> StoreState | None:
        with self._lock:
            return self._store_states.get(store_id)

    def save_order_event(self, event: OrderEvent) -> OrderEvent:
        with self._lock:
            self._order_events[event.event_id] = event
        return event

    def get_latest_order_event(self, order_id: str) -> OrderEvent | None:
        with self._lock:
            events = [
                event
                for event in self._order_events.values()
                if event.order_id == order_id
            ]
        if not events:
            return None
        return max(events, key=lambda event: event.occurred_at)

    def get_latest_store_order_event(
        self,
        store_id: str,
        order_id: str,
    ) -> OrderEvent | None:
        with self._lock:
            events = [
                event
                for event in self._order_events.values()
                if event.store_id == store_id and event.order_id == order_id
            ]
        if not events:
            return None
        return max(events, key=lambda event: event.occurred_at)
