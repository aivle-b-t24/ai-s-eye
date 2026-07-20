from typing import Any
from urllib.parse import quote

import httpx

from .config import get_settings
from .errors import (
    ApiUnavailableError,
    InvalidRequestError,
    SampleDataUnavailableError,
    StoreNotFoundError,
    ToolError,
    UnexpectedResponseError,
)


STATUS_ERRORS: dict[int, type[ToolError]] = {
    404: StoreNotFoundError,
    422: InvalidRequestError,
    503: SampleDataUnavailableError,
}


class StoreApiClient:
    """docs/api-contract.md의 공통 API를 호출한다."""

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        settings = get_settings()
        self._client = httpx.Client(
            base_url=settings.api_base_url,
            timeout=settings.request_timeout_seconds,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "StoreApiClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def get_store_state(self, store_id: str) -> Any:
        return self._get(f"/api/stores/{quote(store_id)}/state")

    def get_eta(self, store_id: str) -> Any:
        return self._get(f"/api/stores/{quote(store_id)}/eta")

    def get_menus(self, store_id: str) -> Any:
        return self._get(f"/api/stores/{quote(store_id)}/menus")

    def get_policies(self, store_id: str) -> Any:
        return self._get(f"/api/stores/{quote(store_id)}/policies")

    def _get(self, path: str) -> Any:
        try:
            response = self._client.get(path)
        except httpx.RequestError as exc:
            raise ApiUnavailableError() from exc

        error = STATUS_ERRORS.get(response.status_code)
        if error is not None:
            raise error()
        if response.status_code >= 400:
            raise UnexpectedResponseError()

        try:
            return response.json()
        except ValueError as exc:
            raise UnexpectedResponseError() from exc
