from threading import RLock
from datetime import datetime, timedelta, timezone
import re

from uuid import uuid4

from .db_repository import StoreNameAlreadyExistsError
from .models import (
    AnalysisJobInfo,
    AnalysisJobStatus,
    CameraRoiConfig,
    CameraRoiConfigInput,
    CameraSceneConfig,
    CameraSceneConfigInput,
    OrderEvent,
    RoiConfigStatus,
    SceneConfigStatus,
    StoreInfo,
    StoreMediaInfo,
    StoreMediaType,
    StoreMenuInput,
    StoreMenuItem,
    StorePolicyInput,
    StorePolicyItem,
    StoreSettings,
    StoreState,
)
from .store_media_storage import new_media_id
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
        self._media: dict[str, StoreMediaInfo] = {}
        self._media_bytes: dict[str, bytes] = {}
        self._media_paths: dict[str, str] = {}
        self._jobs: dict[str, AnalysisJobInfo] = {}
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
            media_ids = [
                media_id
                for media_id, media in self._media.items()
                if media.store_id == store_id
            ]
            for media_id in media_ids:
                self._media.pop(media_id, None)
                self._media_bytes.pop(media_id, None)
                self._media_paths.pop(media_id, None)
            job_ids = [
                job_id
                for job_id, job in self._jobs.items()
                if job.store_id == store_id
            ]
            for job_id in job_ids:
                self._jobs.pop(job_id, None)

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

    def save_store_media(
        self,
        *,
        store_id: str,
        media_type: StoreMediaType,
        filename: str,
        content_type: str,
        content: bytes,
        storage_path: str,
        media_id: str | None = None,
    ) -> StoreMediaInfo:
        media = StoreMediaInfo(
            id=media_id or new_media_id(),
            store_id=store_id,
            media_type=media_type,
            filename=filename,
            content_type=content_type,
            size_bytes=len(content),
            created_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._media[media.id] = media
            self._media_bytes[media.id] = content
            self._media_paths[media.id] = storage_path
        return media

    def list_store_media(self, store_id: str) -> list[StoreMediaInfo]:
        with self._lock:
            items = [m for m in self._media.values() if m.store_id == store_id]
            return sorted(items, key=lambda item: item.created_at, reverse=True)

    def get_store_media(self, media_id: str) -> StoreMediaInfo | None:
        with self._lock:
            return self._media.get(media_id)

    def get_store_media_bytes(self, media_id: str) -> bytes | None:
        with self._lock:
            return self._media_bytes.get(media_id)

    def get_store_media_storage_path(self, media_id: str) -> str | None:
        with self._lock:
            return self._media_paths.get(media_id)

    def create_analysis_job(
        self,
        store_id: str,
        media_id: str,
    ) -> AnalysisJobInfo:
        with self._lock:
            media = self._media.get(media_id)
            if media is None or media.store_id != store_id:
                raise KeyError(media_id)
            job = AnalysisJobInfo(
                id=new_media_id(),
                store_id=store_id,
                media_id=media_id,
                status=AnalysisJobStatus.QUEUED,
                created_at=datetime.now(timezone.utc),
            )
            self._jobs[job.id] = job
            return job

    def list_analysis_jobs(self, store_id: str) -> list[AnalysisJobInfo]:
        with self._lock:
            items = [j for j in self._jobs.values() if j.store_id == store_id]
            return sorted(items, key=lambda item: item.created_at, reverse=True)

    def claim_next_analysis_job(self, worker_id: str) -> AnalysisJobInfo | None:
        with self._lock:
            queued = sorted(
                (
                    job
                    for job in self._jobs.values()
                    if job.status == AnalysisJobStatus.QUEUED
                ),
                key=lambda job: job.created_at,
            )
            if not queued:
                return None
            job = queued[0]
            updated = job.model_copy(
                update={
                    "status": AnalysisJobStatus.RUNNING,
                    "worker_id": worker_id,
                    "claimed_at": datetime.now(timezone.utc),
                }
            )
            self._jobs[job.id] = updated
            return updated

    def update_analysis_job(
        self,
        job_id: str,
        *,
        status: AnalysisJobStatus,
        progress_percent: float | None = None,
        processed_frames: int | None = None,
        total_frames: int | None = None,
        stage_message: str | None = None,
        error_message: str | None = None,
        worker_id: str | None = None,
    ) -> AnalysisJobInfo | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            updates: dict = {"status": status, "error_message": error_message}
            if progress_percent is not None:
                updates["progress_percent"] = progress_percent
            if processed_frames is not None:
                updates["processed_frames"] = processed_frames
            if total_frames is not None:
                updates["total_frames"] = total_frames
            if stage_message is not None:
                updates["stage_message"] = stage_message
            if worker_id is not None:
                updates["worker_id"] = worker_id
            if status in {AnalysisJobStatus.COMPLETED, AnalysisJobStatus.FAILED}:
                updates["completed_at"] = datetime.now(timezone.utc)
                if status == AnalysisJobStatus.COMPLETED and progress_percent is None:
                    updates["progress_percent"] = 100.0
            updated = job.model_copy(update=updates)
            self._jobs[job_id] = updated
            return updated

    def get_analysis_job(self, job_id: str) -> AnalysisJobInfo | None:
        with self._lock:
            return self._jobs.get(job_id)

    def get_store_policies(self, store_id: str) -> list[StorePolicyItem]:
        with self._lock:
            if not hasattr(self, "_policies"):
                self._policies: dict[str, dict[str, StorePolicyItem]] = {}
            store_map = self._policies.get(store_id, {})
            return list(store_map.values())

    def save_store_policy(
        self,
        store_id: str,
        policy_input: StorePolicyInput,
        policy_id: str | None = None,
    ) -> StorePolicyItem:
        with self._lock:
            if not hasattr(self, "_policies"):
                self._policies = {}
            if store_id not in self._policies:
                self._policies[store_id] = {}
            target_id = policy_id or f"policy-{uuid4().hex[:8]}"
            item = StorePolicyItem(
                policy_id=target_id,
                store_id=store_id,
                category=policy_input.category,
                title=policy_input.title,
                content=policy_input.content,
                keywords=policy_input.keywords,
            )
            self._policies[store_id][target_id] = item
            return item

    def delete_store_policy(self, store_id: str, policy_id: str) -> bool:
        with self._lock:
            if not hasattr(self, "_policies") or store_id not in self._policies:
                return False
            if policy_id in self._policies[store_id]:
                del self._policies[store_id][policy_id]
                return True
            return False

    def get_store_menus(self, store_id: str) -> list[StoreMenuItem]:
        with self._lock:
            if not hasattr(self, "_menus"):
                self._menus: dict[str, dict[str, StoreMenuItem]] = {}
            store_map = self._menus.get(store_id, {})
            return list(store_map.values())

    def save_store_menu(
        self,
        store_id: str,
        menu_input: StoreMenuInput,
        menu_id: str | None = None,
    ) -> StoreMenuItem:
        with self._lock:
            if not hasattr(self, "_menus"):
                self._menus = {}
            if store_id not in self._menus:
                self._menus[store_id] = {}
            target_id = menu_id or f"menu-{uuid4().hex[:8]}"
            item = StoreMenuItem(
                menu_id=target_id,
                store_id=store_id,
                category=menu_input.category,
                name=menu_input.name,
                price=menu_input.price,
                prep_minutes=menu_input.prep_minutes,
                available=menu_input.available,
                sold_out_reason=menu_input.sold_out_reason if not menu_input.available else None,
            )
            self._menus[store_id][target_id] = item
            return item

    def toggle_store_menu_sold_out(
        self,
        store_id: str,
        menu_id: str,
        available: bool,
        sold_out_reason: str | None = None,
    ) -> StoreMenuItem | None:
        with self._lock:
            if not hasattr(self, "_menus") or store_id not in self._menus:
                return None
            item = self._menus[store_id].get(menu_id)
            if item is None:
                return None
            updated = item.model_copy(
                update={
                    "available": available,
                    "sold_out_reason": sold_out_reason if not available else None,
                }
            )
            self._menus[store_id][menu_id] = updated
            return updated

    def delete_store_menu(self, store_id: str, menu_id: str) -> bool:
        with self._lock:
            if not hasattr(self, "_menus") or store_id not in self._menus:
                return False
            if menu_id in self._menus[store_id]:
                del self._menus[store_id][menu_id]
                return True
            return False
