from threading import RLock
from datetime import datetime, timezone

from .models import (
    CameraRoiConfig,
    CameraRoiConfigInput,
    OrderEvent,
    RoiConfigStatus,
    StoreState,
)


class InMemoryRepository:
    """Temporary repository used until the team agrees on the DB schema."""

    def __init__(self) -> None:
        self._store_states: dict[str, StoreState] = {}
        self._order_events: dict[str, OrderEvent] = {}
        self._roi_configs: dict[tuple[str, str], list[CameraRoiConfig]] = {}
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

    def save_roi_config(
        self,
        store_id: str,
        camera_id: str,
        config: CameraRoiConfigInput,
    ) -> CameraRoiConfig:
        with self._lock:
            key = (store_id, camera_id)
            history = self._roi_configs.setdefault(key, [])
            history[:] = [
                item.model_copy(update={"status": RoiConfigStatus.ARCHIVED})
                if item.status == RoiConfigStatus.APPROVED
                else item
                for item in history
            ]
            now = datetime.now(timezone.utc)
            saved = CameraRoiConfig(
                **config.model_dump(),
                store_id=store_id,
                camera_id=camera_id,
                version=len(history) + 1,
                status=RoiConfigStatus.APPROVED,
                created_at=now,
                approved_at=now,
            )
            history.append(saved)
            return saved

    def get_approved_roi_config(
        self,
        store_id: str,
        camera_id: str,
    ) -> CameraRoiConfig | None:
        with self._lock:
            return next(
                (
                    item
                    for item in reversed(self._roi_configs.get((store_id, camera_id), []))
                    if item.status == RoiConfigStatus.APPROVED
                ),
                None,
            )

    def list_roi_configs(
        self,
        store_id: str,
        camera_id: str,
    ) -> list[CameraRoiConfig]:
        with self._lock:
            return list(reversed(self._roi_configs.get((store_id, camera_id), [])))

    def approve_roi_config(
        self,
        store_id: str,
        camera_id: str,
        version: int,
    ) -> CameraRoiConfig | None:
        with self._lock:
            history = self._roi_configs.get((store_id, camera_id), [])
            target = next((item for item in history if item.version == version), None)
            if target is None:
                return None
            now = datetime.now(timezone.utc)
            updated: list[CameraRoiConfig] = []
            approved: CameraRoiConfig | None = None
            for item in history:
                if item.version == version:
                    item = item.model_copy(
                        update={
                            "status": RoiConfigStatus.APPROVED,
                            "approved_at": now,
                        }
                    )
                    approved = item
                elif item.status == RoiConfigStatus.APPROVED:
                    item = item.model_copy(update={"status": RoiConfigStatus.ARCHIVED})
                updated.append(item)
            self._roi_configs[(store_id, camera_id)] = updated
            return approved
