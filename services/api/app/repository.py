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

