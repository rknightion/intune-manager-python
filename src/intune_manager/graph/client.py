from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable as CallableABC, Iterable
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Callable, Mapping, Sequence, Tuple

import httpx
from azure.core.credentials import AccessToken, TokenCredential
from kiota_authentication_azure.azure_identity_authentication_provider import (
    AzureIdentityAuthenticationProvider,
)
from httpx._client import UseClientDefault, USE_CLIENT_DEFAULT
from httpx import Auth

from msgraph_beta import GraphServiceClient
from msgraph_core.base_graph_request_adapter import BaseGraphRequestAdapter

from intune_manager.graph.errors import (
    AuthenticationError,
    GraphAPIError,
    GraphErrorCategory,
    PermissionError,
    RateLimitError,
)
from intune_manager.graph.rate_limiter import rate_limiter
from intune_manager.graph.requests import GraphRequest, graph_request_to_batch_entry
from intune_manager.utils import get_logger


logger = get_logger(__name__)


TokenProvider = Callable[[Sequence[str]], AccessToken]


@dataclass(slots=True)
class GraphTelemetryEvent:
    method: str
    url: str
    status_code: int | None
    duration_ms: float
    retries: int
    category: GraphErrorCategory | None
    success: bool


class CallbackTokenCredential(TokenCredential):
    """Wraps a callable token provider to satisfy Azure's credential interface."""

    def __init__(self, provider: TokenProvider) -> None:
        self._provider = provider

    def get_token(
        self,
        *scopes: str,
        claims: str | None = None,
        tenant_id: str | None = None,
        enable_cae: bool = False,
        **kwargs: object,
    ) -> AccessToken:
        del claims, tenant_id, enable_cae, kwargs
        token = self._provider(scopes)
        return token


AuthOption = (
    Tuple[str | bytes, str | bytes]
    | CallableABC[[httpx.Request], httpx.Request]
    | Auth
    | UseClientDefault
    | None
)


class RateLimitedAsyncClient(httpx.AsyncClient):
    def __init__(
        self,
        *args: Any,
        telemetry_callback: Callable[[GraphTelemetryEvent], None] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._telemetry_callback = telemetry_callback

    async def send(
        self,
        request: httpx.Request,
        *,
        stream: bool = False,
        auth: AuthOption = USE_CLIENT_DEFAULT,
        follow_redirects: bool | UseClientDefault = USE_CLIENT_DEFAULT,
        **kwargs: object,
    ) -> httpx.Response:
        is_write = request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
        attempt = 1
        start = time.perf_counter()

        while True:
            while not await rate_limiter.can_make_request(is_write=is_write):
                delay = await rate_limiter.calculate_delay(is_write=is_write)
                await asyncio.sleep(max(delay, 0.05))

            await rate_limiter.record_request(is_write=is_write)

            try:
                response = await super().send(
                    request,
                    stream=stream,
                    auth=auth,
                    follow_redirects=follow_redirects,
                    **kwargs,
                )
            except httpx.TimeoutException as exc:  # pragma: no cover - network path
                if await rate_limiter.should_retry(attempt=attempt, error=exc):
                    delay = await rate_limiter.calculate_retry_delay(attempt=attempt)
                    await asyncio.sleep(delay)
                    attempt += 1
                    continue
                self._publish_telemetry(
                    request,
                    duration=time.perf_counter() - start,
                    status_code=None,
                    success=False,
                    retries=attempt - 1,
                    category=GraphErrorCategory.NETWORK,
                )
                raise GraphAPIError(
                    message="Network timeout communicating with Microsoft Graph",
                    category=GraphErrorCategory.NETWORK,
                    inner_error=exc,
                ) from exc
            except httpx.RequestError as exc:  # pragma: no cover - network path
                self._publish_telemetry(
                    request,
                    duration=time.perf_counter() - start,
                    status_code=None,
                    success=False,
                    retries=attempt - 1,
                    category=GraphErrorCategory.NETWORK,
                )
                raise GraphAPIError(
                    message=f"Network error communicating with Microsoft Graph: {exc}",
                    category=GraphErrorCategory.NETWORK,
                    inner_error=exc,
                ) from exc

            if response.status_code == 429:
                await rate_limiter.record_rate_limit()
                retry_after = response.headers.get("Retry-After")
                if attempt > rate_limiter.max_retries:
                    self._publish_telemetry(
                        request,
                        duration=time.perf_counter() - start,
                        status_code=response.status_code,
                        success=False,
                        retries=attempt - 1,
                        category=GraphErrorCategory.RATE_LIMIT,
                    )
                    raise RateLimitError(retry_after=retry_after)
                delay = await rate_limiter.calculate_retry_delay(
                    attempt=attempt,
                    retry_after_header=retry_after,
                )
                await asyncio.sleep(delay)
                attempt += 1
                continue

            if 400 <= response.status_code:
                error = _map_response_to_error(response)
                self._publish_telemetry(
                    request,
                    duration=time.perf_counter() - start,
                    status_code=response.status_code,
                    success=False,
                    retries=attempt - 1,
                    category=error.category,
                )
                raise error

            await rate_limiter.reset_rate_limit_tracking()
            self._publish_telemetry(
                request,
                duration=time.perf_counter() - start,
                status_code=response.status_code,
                success=True,
                retries=attempt - 1,
                category=None,
            )
            return response

    def _publish_telemetry(
        self,
        request: httpx.Request,
        *,
        duration: float,
        status_code: int | None,
        success: bool,
        retries: int,
        category: GraphErrorCategory | None,
    ) -> None:
        if not self._telemetry_callback:
            return
        event = GraphTelemetryEvent(
            method=request.method,
            url=str(request.url),
            status_code=status_code,
            duration_ms=duration * 1000,
            retries=max(retries, 0),
            category=category,
            success=success,
        )
        try:
            self._telemetry_callback(event)
        except Exception:  # pragma: no cover - telemetry shouldn't break requests
            logger.warning("Telemetry callback raised an exception", exc_info=True)


def _map_response_to_error(response: httpx.Response) -> GraphAPIError:
    status = response.status_code
    retry_after = response.headers.get("Retry-After")
    content_type = response.headers.get("Content-Type", "")
    body: dict[str, object] = {}
    try:
        if "json" in content_type:
            body = response.json()
        else:
            body = json.loads(response.text)
    except Exception:  # pragma: no cover - fallback
        body = {}

    error_info = body.get("error") if isinstance(body, dict) else None
    code = None
    message = None
    if isinstance(error_info, dict):
        code = error_info.get("code")
        message = error_info.get("message")

    message = message or response.text or f"Graph request failed with status {status}"

    if status == 401:
        return AuthenticationError(message=message)
    if status == 403:
        return PermissionError(message=message)
    if status == 429:
        return RateLimitError(message=message, retry_after=retry_after)

    category = GraphErrorCategory.UNKNOWN
    if 500 <= status <= 599:
        category = GraphErrorCategory.UNKNOWN
    elif status == 409:
        category = GraphErrorCategory.CONFLICT
    elif status in {400, 404}:
        category = GraphErrorCategory.VALIDATION

    return GraphAPIError(
        message=message,
        category=category,
        status_code=status,
        code=code if isinstance(code, str) else None,
        retry_after=retry_after,
    )


@dataclass(slots=True)
class GraphClientConfig:
    scopes: Sequence[str]
    user_agent: str = "IntuneManager-Python"
    telemetry_namespace: str = "intune-manager"
    api_version: str = "beta"
    page_size: int = 100
    enable_telemetry: bool = True
    telemetry_callback: Callable[[GraphTelemetryEvent], None] | None = None


class GraphClientFactory:
    def __init__(
        self, token_provider: TokenProvider, config: GraphClientConfig
    ) -> None:
        self._credential = CallbackTokenCredential(token_provider)
        self._config = config
        self._telemetry_callback = (
            config.telemetry_callback if config.enable_telemetry else None
        )
        self._http_client: RateLimitedAsyncClient | None = None

    def create_client(self) -> GraphServiceClient:
        http_client = self._get_http_client()
        auth_provider = AzureIdentityAuthenticationProvider(
            credentials=self._credential,
            scopes=list(self._config.scopes),
        )
        adapter = BaseGraphRequestAdapter(
            authentication_provider=auth_provider,
            http_client=http_client,
        )
        return GraphServiceClient(adapter)

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
        api_version: str | None = None,
    ) -> httpx.Response:
        client = self._get_http_client()
        url = self._absolute_url(path, api_version=api_version)
        response = await client.request(
            method,
            url,
            params=params,
            json=json_body,
            data=data,
            content=content,
            headers=headers,
        )
        return response

    async def request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        headers: dict[str, str] | None = None,
        api_version: str | None = None,
    ) -> dict[str, Any]:
        response = await self.request(
            method,
            path,
            params=params,
            json_body=json_body,
            headers=headers,
            api_version=api_version,
        )
        return response.json()

    async def request_bytes(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        api_version: str | None = None,
    ) -> bytes:
        response = await self.request(
            method,
            path,
            params=params,
            headers=headers,
            api_version=api_version,
        )
        return response.content

    async def iter_collection(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        page_size: int | None = None,
        api_version: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        next_url = self._absolute_url(path, api_version=api_version)
        query: dict[str, Any] | None = dict(params or {})
        if page_size is None:
            page_size = self._config.page_size
        if query is not None and "$top" not in query and page_size:
            query["$top"] = page_size
        elif query is None and page_size:
            query = {"$top": page_size}

        while next_url:
            payload = await self.request_json(
                method,
                next_url,
                params=query,
                headers=headers,
                api_version=api_version if not next_url.startswith("http") else None,
            )
            value = payload.get("value")
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        yield item
                    else:
                        yield {"value": item}
            else:
                yield payload
                break
            next_link = payload.get("@odata.nextLink")
            if not next_link:
                break
            next_url = next_link
            query = None

    async def execute_batch(
        self,
        requests: Iterable[GraphRequest | Mapping[str, Any]],
        *,
        api_version: str | None = None,
    ) -> dict[str, Any]:
        payload = {"requests": []}
        for index, request in enumerate(requests, start=1):
            if isinstance(request, GraphRequest):
                entry = graph_request_to_batch_entry(
                    request,
                    request_id=str(index),
                )
            else:
                entry = dict(request)
                entry.setdefault("id", str(index))
                if entry.get("url") is None:
                    raise ValueError("Batch request entries must include a 'url'")
            payload["requests"].append(entry)

        if not payload["requests"]:
            return {"responses": []}

        return await self.request_json(
            "POST",
            "/$batch",
            json_body=payload,
            headers={"Content-Type": "application/json"},
            api_version=api_version,
        )

    async def close(self) -> None:
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    # ------------------------------------------------------------- Internals

    def _get_http_client(self) -> RateLimitedAsyncClient:
        if self._http_client is None:
            callback = self._telemetry_callback
            if callback is None and self._config.enable_telemetry:
                callback = self._default_telemetry_callback
            self._http_client = RateLimitedAsyncClient(
                headers={"User-Agent": self._config.user_agent},
                telemetry_callback=callback,
            )
        return self._http_client

    def _absolute_url(self, path: str, api_version: str | None = None) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        version = api_version or self._config.api_version
        return f"https://graph.microsoft.com/{version}{path}"

    def _default_telemetry_callback(self, event: GraphTelemetryEvent) -> None:
        logger.debug(
            "Graph request",
            method=event.method,
            url=event.url,
            status_code=event.status_code,
            duration_ms=round(event.duration_ms, 2),
            retries=event.retries,
            success=event.success,
            category=event.category.value if event.category else None,
        )


__all__ = [
    "GraphClientFactory",
    "GraphClientConfig",
    "TokenProvider",
    "CallbackTokenCredential",
    "GraphTelemetryEvent",
]
