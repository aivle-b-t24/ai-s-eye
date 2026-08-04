"""카카오 유저별로 '지금 어느 매장을 보고 있는지'를 잠깐 기억한다.

공용 채널 하나로 여러 매장을 처리하려면, 손님이 한 번 고른(또는 QR로 들어온) 매장을
다음 발화에서도 이어써야 한다. 그 상태를 담는 아주 작은 저장소다.

occupancy와 마찬가지로 **프로세스 메모리**라 컨테이너를 재시작하면 사라진다. 단일 AICC
컨테이너로 도는 데모에는 충분하고, 여러 프로세스로 확장하면 Redis 등으로 바꾸면 된다.
"""

import time
from threading import RLock
from typing import Callable


class SessionStore:
    def __init__(
        self,
        ttl_seconds: float = 1800.0,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._data: dict[str, tuple[str, float]] = {}
        self._lock = RLock()

    def get(self, user_id: str | None) -> str | None:
        if not user_id:
            return None
        with self._lock:
            item = self._data.get(user_id)
            if item is None:
                return None
            store_id, expires_at = item
            if expires_at < self._clock():
                self._data.pop(user_id, None)
                return None
            return store_id

    def set(self, user_id: str | None, store_id: str) -> None:
        if not user_id:
            return
        with self._lock:
            self._data[user_id] = (store_id, self._clock() + self._ttl)

    def clear(self, user_id: str | None) -> None:
        if not user_id:
            return
        with self._lock:
            self._data.pop(user_id, None)
