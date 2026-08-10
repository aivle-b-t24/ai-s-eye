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


def parse_name_overlay(raw: str | None) -> dict[str, str]:
    """`AICC_STORE_DIRECTORY`(JSON)에서 매장 표시명 오버레이만 뽑는다: {store_id: 이름}.

    백엔드 매장 목록은 ID만 주므로, 여기 있는 매장은 예쁜 이름으로 보여주고 없는 매장은
    ID를 이름 대신 쓴다. 즉 '새 매장은 자동 등장, 이름은 선택'이다."""
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        logger.warning("AICC_STORE_DIRECTORY 파싱 실패 — 이름 오버레이 없이 진행", exc_info=True)
        return {}
    overlay: dict[str, str] = {}
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            store_id = item.get("id") or item.get("store_id")
            name = item.get("name")
            if store_id and name:
                overlay[str(store_id)] = str(name)
    return overlay


def directory_from_ids(
    store_ids: list[str],
    name_overlay: dict[str, str] | None = None,
) -> StoreDirectory:
    """백엔드가 준 매장 ID 목록으로 디렉터리를 만든다. 이름은 오버레이에 있으면 그걸,
    없으면 store_id를 표시명으로 쓴다."""
    overlay = name_overlay or {}
    return StoreDirectory(
        [StoreEntry(id=store_id, name=overlay.get(store_id, store_id)) for store_id in store_ids]
    )


def directory_from_items(
    items: list[dict],
    name_overlay: dict[str, str] | None = None,
) -> StoreDirectory:
    """백엔드 매장 목록(각 {store_id, name})으로 디렉터리를 만든다.

    표시명 우선순위: 백엔드 name → 설정 오버레이 → store_id. 백엔드(매장 마스터)가
    이름을 주면 설정 없이도 예쁜 이름이 나온다(이름의 단일 출처)."""
    overlay = name_overlay or {}
    entries: list[StoreEntry] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        store_id = item.get("store_id")
        if not store_id:
            continue
        name = item.get("name") or overlay.get(store_id) or store_id
        entries.append(StoreEntry(id=str(store_id), name=str(name)))
    return StoreDirectory(entries)


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
