from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from typing import Any


class StubPublicClientApplication:
    """Lightweight stand-in for msal.PublicClientApplication."""

    def __init__(
        self,
        client_id: str,
        authority: str,
        token_cache=None,
        *,
        accounts: Iterable[dict[str, Any]] | None = None,
        silent_results: Iterable[dict[str, Any] | None] | None = None,
        interactive_results: Iterable[dict[str, Any]] | None = None,
    ) -> None:
        self.client_id = client_id
        self.authority = authority
        self.token_cache = token_cache
        self._accounts = list(accounts or [])
        self._silent_results = list(silent_results or [])
        self._interactive_results = list(interactive_results or [])
        self.acquire_token_silent_calls: list[
            tuple[tuple[str, ...], dict[str, Any] | None]
        ] = []
        self.acquire_token_interactive_calls: list[
            tuple[tuple[str, ...], dict[str, Any] | None]
        ] = []
        self.remove_account_calls: list[dict[str, Any]] = []

    def get_accounts(self) -> list[dict[str, Any]]:
        return list(self._accounts)

    def acquire_token_silent(
        self,
        scopes: Iterable[str],
        *,
        account: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        self.acquire_token_silent_calls.append((tuple(scopes), account))
        if self._silent_results:
            return self._silent_results.pop(0)
        return None

    def acquire_token_interactive(
        self,
        scopes: Iterable[str],
        prompt: str | None = None,
    ) -> dict[str, Any]:
        self.acquire_token_interactive_calls.append((tuple(scopes), {"prompt": prompt}))
        if not self._interactive_results:
            raise RuntimeError("No interactive result configured")
        result = self._interactive_results.pop(0)
        if isinstance(result, dict):
            claims = (
                result.get("id_token_claims", {}) if isinstance(result, dict) else {}
            )
            account = {
                "name": claims.get("name"),
                "username": claims.get("preferred_username"),
                "home_account_id": claims.get("oid"),
                "environment": claims.get("tid"),
            }
            if account["username"]:
                self._accounts.append(account)
            self._silent_results.append(result)
        return result

    def remove_account(self, account: dict[str, Any]) -> None:
        self.remove_account_calls.append(account)
        try:
            self._accounts.remove(account)
        except ValueError:
            pass


@dataclass(slots=True)
class FakeResponse:
    status_code: int = 200
    json_payload: dict[str, Any] | None = None
    headers: dict[str, str] | None = None
    content: bytes = b""

    def __post_init__(self) -> None:
        if self.headers is None:
            self.headers = {}

    def json(self) -> dict[str, Any]:
        return dict(self.json_payload or {})


class FakeGraphClientFactory:
    """Deterministic Graph client facade for service tests."""

    def __init__(self) -> None:
        self.collections: dict[str, list[dict[str, Any]]] = {}
        self.recorded_requests: list[tuple[str, str, dict[str, Any]]] = []
        self.request_responses: dict[tuple[str, str], dict[str, Any] | Exception] = {}
        self.batch_response: dict[str, Any] = {"responses": []}
        self.batch_exception: Exception | None = None
        self.executed_batches: list[list[Any]] = []

    def set_collection(self, path: str, items: Iterable[dict[str, Any]]) -> None:
        self.collections[path] = list(items)

    def set_request_json_response(
        self,
        method: str,
        path: str,
        response: dict[str, Any] | Exception,
    ) -> None:
        self.request_responses[(method, path)] = response

    def set_batch_response(self, response: dict[str, Any]) -> None:
        self.batch_response = response
        self.batch_exception = None

    def set_batch_exception(self, exc: Exception) -> None:
        self.batch_exception = exc

    async def iter_collection(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        page_size: int | None = None,
        api_version=None,
        cancellation_token=None,
    ) -> AsyncIterator[dict[str, Any]]:
        for item in self.collections.get(path, []):
            if asyncio.iscoroutine(item):
                yield await item
            else:
                yield item

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        data: Any | None = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        api_version=None,
        cancellation_token=None,
    ) -> FakeResponse:
        payload = {
            "params": params,
            "json": json_body,
            "data": data,
            "content": content,
            "headers": headers,
            "api_version": api_version,
        }
        self.recorded_requests.append((method, path, payload))
        configured = self.request_responses.get((method, path))
        if isinstance(configured, Exception):
            raise configured
        if isinstance(configured, dict):
            return FakeResponse(status_code=200, json_payload=configured)
        return FakeResponse(status_code=204)

    async def request_json(
        self, method: str, path: str, **kwargs: Any
    ) -> dict[str, Any]:
        response = await self.request(method, path, **kwargs)
        return response.json()

    async def execute_batch(
        self,
        requests: Iterable[Any],
        *,
        api_version=None,
        cancellation_token=None,
    ) -> dict[str, Any]:
        batch_list = list(requests)
        self.executed_batches.append(batch_list)
        if self.batch_exception is not None:
            raise self.batch_exception
        return dict(self.batch_response)
