from typing import Any

from .client import StoreApiClient
from .config import get_settings
from .errors import ToolError, UnexpectedResponseError


def _failure(error: ToolError) -> dict[str, Any]:
    return {"ok": False, "error": error.code, "message": error.message}


def _fields(body: Any, *keys: str) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise UnexpectedResponseError()
    try:
        return {key: body[key] for key in keys}
    except KeyError as exc:
        raise UnexpectedResponseError() from exc


def _normalize(value: str) -> str:
    return "".join(value.split()).lower()


def _menu_summary(menu: Any) -> dict[str, Any]:
    return _fields(menu, "menu_id", "name", "price", "available", "sold_out_reason")


class StoreTools:
    """고객 질문에 답할 때 호출하는 Tool 모음.

    오류는 예외로 던지지 않고 ok=False 결과로 돌려준다. LLM이 대화를 끊지 않고
    고객에게 상황을 설명할 수 있어야 하기 때문이다.
    """

    def __init__(self, client: StoreApiClient | None = None) -> None:
        self._client = client if client is not None else StoreApiClient()
        self._default_store_id = get_settings().default_store_id

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "StoreTools":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def get_store_state(self, store_id: str | None = None) -> dict[str, Any]:
        target = self._store(store_id)
        try:
            body = self._client.get_store_state(target)
            data = _fields(
                body,
                "visible_person_count",
                "queue_count_estimate",
                "quality_status",
                "captured_at",
            )
        except ToolError as exc:
            return _failure(exc)
        return {"ok": True, "store_id": target, **data}

    def get_eta(self, store_id: str | None = None) -> dict[str, Any]:
        target = self._store(store_id)
        try:
            body = self._client.get_eta(target)
            data = _fields(body, "estimated_wait_minutes", "data_source")
        except ToolError as exc:
            return _failure(exc)
        return {"ok": True, "store_id": target, **data}

    def get_menus(
        self,
        store_id: str | None = None,
        menu_name: str | None = None,
    ) -> dict[str, Any]:
        target = self._store(store_id)
        try:
            body = self._client.get_menus(target)
            menus = [_menu_summary(menu) for menu in _menu_list(body)]
        except ToolError as exc:
            return _failure(exc)

        if menu_name is None:
            return {"ok": True, "store_id": target, "menus": menus}

        wanted = _normalize(menu_name)
        matched = [
            menu
            for menu in menus
            if wanted in _normalize(str(menu["name"])) or wanted == _normalize(str(menu["menu_id"]))
        ]
        result = {"ok": True, "store_id": target, "menus": matched}
        if not matched:
            result["message"] = f"'{menu_name}' 메뉴는 이 매장에 없습니다."
        return result

    def get_policies(self, store_id: str | None = None) -> dict[str, Any]:
        target = self._store(store_id)
        try:
            body = self._client.get_policies(target)
            policies = [
                _fields(policy, "policy_id", "title", "content")
                for policy in _policy_list(body)
            ]
        except ToolError as exc:
            return _failure(exc)
        return {"ok": True, "store_id": target, "policies": policies}

    def _store(self, store_id: str | None) -> str:
        return store_id or self._default_store_id


def _menu_list(body: Any) -> list[Any]:
    return _item_list(body, "menus")


def _policy_list(body: Any) -> list[Any]:
    return _item_list(body, "policies")


def _item_list(body: Any, key: str) -> list[Any]:
    if not isinstance(body, dict):
        raise UnexpectedResponseError()
    items = body.get(key)
    if not isinstance(items, list):
        raise UnexpectedResponseError()
    return items
