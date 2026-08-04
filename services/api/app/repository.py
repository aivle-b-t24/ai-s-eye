from threading import RLock
from datetime import datetime, timedelta, timezone
import re

from .db_repository import StoreNameAlreadyExistsError
from .models import (
    CameraRoiConfig,
    CameraRoiConfigInput,
    CameraSceneConfig,
    CameraSceneConfigInput,
    OrderEvent,
    RoiConfigStatus,
    SceneConfigStatus,
    StoreInfo,
    StoreSettings,
    StoreState,
)
from .order_queue import build_waiting_intervals, concurrency_at

WAITING_LOOKUP_WINDOW = timedelta(hours=1)
_STORE_ID_PATTERN = re.compile(r"^store-(\d+)$")
_DEFAULT_STORE_NAMES = {
    "store-001": "동명점",
    "store-002": "수완점",
}


class InMemoryRepository:
    """Temporary repository used until the team agrees on the DB schema."""

    def __init__(self) -> None:
        now = datetime.now(timezone.utc)
        self._stores: dict[str, StoreInfo] = {
            store_id: StoreInfo(
                id=store_id,
                name=name,
                created_at=now,
                updated_at=now,
            )
            for store_id, name in _DEFAULT_STORE_NAMES.items()
        }
        self._store_states: dict[str, StoreState] = {}
        self._store_settings: dict[str, StoreSettings] = {}
        self._order_events: dict[str, OrderEvent] = {}
        self._roi_configs: dict[tuple[str, str], list[CameraRoiConfig]] = {}
        self._scene_configs: dict[tuple[str, str], list[CameraSceneConfig]] = {}
        self._lock = RLock()

    def save_store_state(self, state: StoreState) -> StoreState:
        with self._lock:
            self._store_states[state.store_id] = state
        return state

    def get_store_state(self, store_id: str) -> StoreState | None:
        with self._lock:
            return self._store_states.get(store_id)

    def list_stores(self) -> list[StoreInfo]:
        with self._lock:
            return sorted(self._stores.values(), key=lambda store: store.id)

    def get_store(self, store_id: str) -> StoreInfo | None:
        with self._lock:
            return self._stores.get(store_id)

    def store_exists(self, store_id: str) -> bool:
        with self._lock:
            return store_id in self._stores

    def create_store(self, name: str) -> StoreInfo:
        with self._lock:
            if any(store.name == name for store in self._stores.values()):
                raise StoreNameAlreadyExistsError(name)
            max_number = 0
            for store_id in self._stores:
                match = _STORE_ID_PATTERN.match(store_id)
                if match:
                    max_number = max(max_number, int(match.group(1)))
            store_id = f"store-{max_number + 1:03d}"
            now = datetime.now(timezone.utc)
            store = StoreInfo(
                id=store_id,
                name=name,
                created_at=now,
                updated_at=now,
            )
            self._stores[store_id] = store
            return store

    def delete_store(self, store_id: str) -> None:
        with self._lock:
            self._stores.pop(store_id, None)

    def get_store_settings(self, store_id: str) -> StoreSettings | None:
        with self._lock:
            return self._store_settings.get(store_id)

    def save_store_settings(self, store_id: str, max_capacity: int) -> StoreSettings:
        settings = StoreSettings(
            store_id=store_id,
            max_capacity=max_capacity,
            updated_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._store_settings[store_id] = settings
        return settings

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

    def list_order_events(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
        store_id: str | None = None,
    ) -> list[OrderEvent]:
        """CSV 내보내기에 사용할 기간 내 주문 이벤트를 반환한다."""
        with self._lock:
            events = [
                event
                for event in self._order_events.values()
                if start_at <= event.occurred_at < end_at
                and (store_id is None or event.store_id == store_id)
            ]
        return sorted(
            events,
            key=lambda event: (
                event.occurred_at,
                event.store_id,
                event.order_id,
                event.event_id,
            ),
        )

    def count_waiting_orders_at(self, store_id: str, at: datetime) -> int:
        """주어진 시각에 진행 중(접수~픽업 전)인 주문 수 = 그 순간 대기 인원."""
        orders = self.list_order_events(
            start_at=at - WAITING_LOOKUP_WINDOW,
            end_at=at + WAITING_LOOKUP_WINDOW,
            store_id=store_id,
        )
        intervals = build_waiting_intervals(orders)
        return concurrency_at(intervals, at)

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

    def save_scene_config(
        self,
        store_id: str,
        camera_id: str,
        config: CameraSceneConfigInput,
    ) -> CameraSceneConfig:
        with self._lock:
            key = (store_id, camera_id)
            history = self._scene_configs.setdefault(key, [])
            history[:] = [
                item.model_copy(update={"status": SceneConfigStatus.ARCHIVED})
                if item.status == SceneConfigStatus.APPROVED
                else item
                for item in history
            ]
            now = datetime.now(timezone.utc)
            saved = CameraSceneConfig(
                **config.model_dump(),
                store_id=store_id,
                camera_id=camera_id,
                version=len(history) + 1,
                status=SceneConfigStatus.APPROVED,
                created_at=now,
                approved_at=now,
            )
            history.append(saved)
            return saved

    def get_approved_scene_config(
        self,
        store_id: str,
        camera_id: str,
    ) -> CameraSceneConfig | None:
        with self._lock:
            return next(
                (
                    item
                    for item in reversed(self._scene_configs.get((store_id, camera_id), []))
                    if item.status == SceneConfigStatus.APPROVED
                ),
                None,
            )

    def list_scene_configs(
        self,
        store_id: str,
        camera_id: str,
    ) -> list[CameraSceneConfig]:
        with self._lock:
            return list(reversed(self._scene_configs.get((store_id, camera_id), [])))

    def approve_scene_config(
        self,
        store_id: str,
        camera_id: str,
        version: int,
    ) -> CameraSceneConfig | None:
        with self._lock:
            history = self._scene_configs.get((store_id, camera_id), [])
            target = next((item for item in history if item.version == version), None)
            if target is None:
                return None
            now = datetime.now(timezone.utc)
            updated: list[CameraSceneConfig] = []
            approved: CameraSceneConfig | None = None
            for item in history:
                if item.version == version:
                    item = item.model_copy(
                        update={
                            "status": SceneConfigStatus.APPROVED,
                            "approved_at": now,
                        }
                    )
                    approved = item
                elif item.status == SceneConfigStatus.APPROVED:
                    item = item.model_copy(update={"status": SceneConfigStatus.ARCHIVED})
                updated.append(item)
            self._scene_configs[(store_id, camera_id)] = updated
            return approved
