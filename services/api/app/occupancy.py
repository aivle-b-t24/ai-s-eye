from threading import RLock

from .models import TwinFrame


class LatestOccupancyRepository:
    """매장별 최신 위치 프레임만 메모리에 보관한다."""

    def __init__(self) -> None:
        self._frames: dict[str, TwinFrame] = {}
        self._lock = RLock()

    def save(self, frame: TwinFrame) -> TwinFrame:
        with self._lock:
            self._frames[frame.store_id] = frame
        return frame

    def get(self, store_id: str) -> TwinFrame | None:
        with self._lock:
            return self._frames.get(store_id)

    def clear(self) -> None:
        with self._lock:
            self._frames.clear()
