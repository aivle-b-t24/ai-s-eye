from typing import Any
from urllib.parse import quote

import httpx

from .config import get_settings
from .errors import (
    ApiUnavailableError,
    InvalidRequestError,
    OrderNotFoundError,
    SampleDataUnavailableError,
    StoreNotFoundError,
    ToolError,
    UnexpectedResponseError,
)


STATUS_ERRORS: dict[int, type[ToolError]] = {
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

    def get_order(self, order_id: str) -> Any:
        return self._get(
            f"/api/orders/{quote(order_id)}",
            not_found=OrderNotFoundError,
        )

    def get_store_summary(
        self,
        start_at: str | None = None,
        end_at: str | None = None,
    ) -> Any:
        """기간별 매장 집계를 조회한다. GET /api/stores/summary.

        start_at/end_at은 있으면 쿼리로 넘긴다. 없으면 집계 API 기본 기간을 따른다.
        기간 파라미터 이름은 공통 API 확정 시 맞춘다.
        """
        params = {k: v for k, v in (("start_at", start_at), ("end_at", end_at)) if v}
        return self._get("/api/stores/summary", params=params or None)

    def _get(
        self,
        path: str,
        not_found: type[ToolError] = StoreNotFoundError,
        params: dict[str, str] | None = None,
    ) -> Any:
        try:
            response = self._client.get(path, params=params)
        except httpx.RequestError as exc:
            raise ApiUnavailableError() from exc

        if response.status_code == 404:
            raise not_found()
        error = STATUS_ERRORS.get(response.status_code)
        if error is not None:
            raise error()
        if response.status_code >= 400:
            raise UnexpectedResponseError()

        try:
            return response.json()
        except ValueError as exc:
            raise UnexpectedResponseError() from exc
