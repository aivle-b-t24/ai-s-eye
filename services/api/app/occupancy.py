"""매장별 최신 occupancy 프레임 저장소.

메모리 캐시 + (DATABASE_URL이 있을 때) Postgres `current_store_occupancy`에
영속화해서 API 재시작 후에도 트윈 agents를 복구한다.
"""

from __future__ import annotations

import logging
from threading import RLock

from sqlalchemy.dialects.postgresql import insert

from .models import TwinFrame

logger = logging.getLogger(__name__)


class LatestOccupancyRepository:
    """매장별 최신 위치 프레임을 메모리(+DB)에 보관한다."""

    def __init__(self, *, persist: bool | None = None) -> None:
        self._frames: dict[str, TwinFrame] = {}
        self._lock = RLock()
        if persist is None:
            from .config import get_settings

            persist = bool(get_settings().database_url)
        self._persist = persist

    def save(self, frame: TwinFrame) -> TwinFrame:
        with self._lock:
            self._frames[frame.store_id] = frame
        if self._persist:
            self._persist_frame(frame)
        return frame

    def get(self, store_id: str) -> TwinFrame | None:
        with self._lock:
            cached = self._frames.get(store_id)
            if cached is not None:
                return cached
        if not self._persist:
            return None
        loaded = self._load_frame(store_id)
        if loaded is None:
            return None
        with self._lock:
            self._frames[store_id] = loaded
        return loaded

    def clear(self) -> None:
        with self._lock:
            self._frames.clear()

    def _persist_frame(self, frame: TwinFrame) -> None:
        try:
            import sqlalchemy as sa

            from .database import get_session_factory
            from .db_models import CurrentStoreOccupancyRecord

            payload = frame.model_dump(mode="json", exclude_none=True)
            session_factory = get_session_factory()
            with session_factory() as session:
                statement = insert(CurrentStoreOccupancyRecord).values(
                    store_id=frame.store_id,
                    payload=payload,
                )
                statement = statement.on_conflict_do_update(
                    index_elements=[CurrentStoreOccupancyRecord.store_id],
                    set_={
                        "payload": statement.excluded.payload,
                        "updated_at": sa.text("CURRENT_TIMESTAMP"),
                    },
                )
                session.execute(statement)
                session.commit()
        except Exception:  # noqa: BLE001 — 영속화 실패해도 메모리 저장은 유지
            logger.exception("occupancy persist failed store=%s", frame.store_id)

    def _load_frame(self, store_id: str) -> TwinFrame | None:
        try:
            from .database import get_session_factory
            from .db_models import CurrentStoreOccupancyRecord

            session_factory = get_session_factory()
            with session_factory() as session:
                record = session.get(CurrentStoreOccupancyRecord, store_id)
                if record is None:
                    return None
                return TwinFrame.model_validate(record.payload)
        except Exception:  # noqa: BLE001
            logger.exception("occupancy load failed store=%s", store_id)
            return None
