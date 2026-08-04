"""공용 채널이 안내할 수 있는 매장 목록(이름 포함).

지금은 백엔드에 '매장 레지스트리(매장 이름)' API가 없어서(이름은 대시보드 프론트에만
있다) AICC 설정값 `AICC_STORE_DIRECTORY`(JSON)에서 읽는다. 새 매장은 이 목록에 한 줄만
추가하면 대화 선택지(퀵리플라이)에 **자동으로** 등장한다. 나중에 백엔드에 매장 목록
API가 생기면 load 함수만 그쪽을 보게 바꾸면 되고, 나머지 로직은 그대로다.
"""

import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoreEntry:
    id: str
    name: str


def _normalize(text: str) -> str:
    return "".join(str(text).split()).lower()


class StoreDirectory:
    def __init__(self, entries: list[StoreEntry]) -> None:
        self._entries = list(entries)
        self._by_id = {entry.id: entry for entry in self._entries}

    def list(self) -> list[StoreEntry]:
        return list(self._entries)

    def has_multiple(self) -> bool:
        return len(self._entries) > 1

    def contains(self, store_id: str) -> bool:
        return store_id in self._by_id

    def name_of(self, store_id: str) -> str:
        entry = self._by_id.get(store_id)
        return entry.name if entry else store_id

    def resolve(self, text: str) -> str | None:
        """손님이 친(또는 버튼으로 누른) 말에서 매장을 알아낸다.

        버튼 탭('동명점')과 '동명점 붐벼요?'처럼 이름으로 시작하는 경우, 그리고 store_id를
        직접 친 경우를 잡는다. 문장 한가운데 우연히 이름이 들어간 경우는 잡지 않는다."""
        norm = _normalize(text)
        if not norm:
            return None
        for entry in self._entries:
            id_norm = _normalize(entry.id)
            name_norm = _normalize(entry.name)
            if norm == id_norm or norm == name_norm or norm.startswith(name_norm):
                return entry.id
        return None


def load_store_directory(raw: str | None) -> StoreDirectory:
    """`AICC_STORE_DIRECTORY` 원문(JSON 배열)을 StoreDirectory로 만든다.

    형식: [{"id": "store-001", "name": "동명점"}, ...] (id 대신 store_id도 허용).
    비었거나 형식이 잘못되면 빈 디렉터리로 물러난다(단일 매장 기본 동작 유지)."""
    if not raw or not raw.strip():
        return StoreDirectory([])
    try:
        data = json.loads(raw)
    except ValueError:
        logger.warning("AICC_STORE_DIRECTORY 파싱 실패 — 빈 디렉터리로 진행", exc_info=True)
        return StoreDirectory([])
    entries: list[StoreEntry] = []
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            store_id = item.get("id") or item.get("store_id")
            if not store_id:
                continue
            name = item.get("name") or store_id
            entries.append(StoreEntry(id=str(store_id), name=str(name)))
    return StoreDirectory(entries)
