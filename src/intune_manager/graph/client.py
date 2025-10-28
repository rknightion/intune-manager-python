from __future__ import annotations

import asyncio
import json
import shlex
import time
from collections.abc import Callable as CallableABC, Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    AsyncGenerator,
    Awaitable,
    Callable,
    Mapping,
    Sequence,
    Tuple,
    TypeAlias,
    TypeVar,
)

import httpx
from httpx._client import UseClientDefault, USE_CLIENT_DEFAULT
from httpx import Auth

from intune_manager.auth.types import AccessToken

from intune_manager.graph.errors import (
    AuthenticationError,
    GraphAPIError,
    GraphErrorCategory,
    PermissionError,
    RateLimitError,
)
from intune_manager.graph.rate_limiter import rate_limiter
from intune_manager.graph.requests import GraphRequest, graph_request_to_batch_entry
from intune_manager.utils import CancellationToken, get_logger


logger = get_logger(__name__)


TokenProvider = Callable[[Sequence[str]], AccessToken]

T = TypeVar("T")


class GraphAPIVersion(str, Enum):
    """Supported Microsoft Graph API versions for the client factory."""

    V1 = "v1.0"
    BETA = "beta"


ApiVersionInput: TypeAlias = GraphAPIVersion | str | None


DEFAULT_VERSION_OVERRIDES: dict[str, str] = {
    "/deviceManagement/configurationPolicies": GraphAPIVersion.BETA.value,
    "/deviceManagement/assignmentFilters": GraphAPIVersion.BETA.value,
    "/deviceManagement/auditEvents": GraphAPIVersion.BETA.value,
    "/deviceManagement/managedDevices": GraphAPIVersion.BETA.value,
}


@dataclass(slots=True)
class GraphTelemetryEvent:
    method: str
    url: str
    status_code: int | None
    duration_ms: float
    retries: int
    category: GraphErrorCategory | None
    success: bool


def _coerce_api_version(value: GraphAPIVersion | str) -> str:
    """Normalise API version inputs to canonical string values."""

    if isinstance(value, GraphAPIVersion):
        return value.value
    normalised = value.strip()
    lowered = normalised.lower()
    if lowered in {"v1", "v1.0", "1.0", "ga"}:
        return GraphAPIVersion.V1.value
    if lowered == "beta":
        return GraphAPIVersion.BETA.value
    return normalised


def _prepare_relative_path(path: str) -> tuple[str, str | None]:
    """Return a leading-slash path without version plus any embedded version."""

    trimmed = path.strip()
    host = "graph.microsoft.com"
    for scheme in ("https://", "http://"):
        prefix = f"{scheme}{host}"
        if trimmed.startswith(prefix):
            trimmed = trimmed[len(prefix) :]
            break
    if not trimmed.startswith("/"):
        trimmed = "/" + trimmed

    version: str | None = None
    for prefix, mapped in (
        ("/beta", GraphAPIVersion.BETA.value),
        ("/v1.0", GraphAPIVersion.V1.value),
        ("/v1", GraphAPIVersion.V1.value),
        ("/1.0", GraphAPIVersion.V1.value),
    ):
        if trimmed == prefix:
            version = mapped
            trimmed = "/"
            break
        candidate = f"{prefix}/"
        if trimmed.startswith(candidate):
            version = mapped
            trimmed = trimmed[len(prefix) :]
            if not trimmed.startswith("/"):
                trimmed = "/" + trimmed
            break

    if trimmed != "/" and trimmed.endswith("/"):
        trimmed = trimmed.rstrip("/")
    return trimmed or "/", version


def _normalise_override_key(path: str) -> str:
    """Normalise override keys to allow loose user input (with/without host)."""

    trimmed = path.strip()
    host = "graph.microsoft.com/"
    for scheme in ("https://", "http://"):
        prefix = f"{scheme}{host}"
        if trimmed.startswith(prefix):
            trimmed = trimmed[len(prefix) :]
            break

    relative, _ = _prepare_relative_path(trimmed)
    return relative


def _prefix_matches(prefix: str, path: str) -> bool:
    """Determine whether an override prefix applies to a path boundary."""

    if prefix in {"", "/"}:
        return True
    if path == prefix:
        return True
    if not path.startswith(prefix):
        return False
    boundary_index = len(prefix)
    if boundary_index >= len(path):
        return True
    return path[boundary_index] == "/"


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

    async def _await_with_cancellation(
        self,
        coro: Awaitable[T],
        token: CancellationToken | None,
    ) -> T:
        if token is None:
            return await coro
        token.raise_if_cancelled()
        task = asyncio.create_task(coro)
        unlink = token.link_task(task)
        try:
            return await task
        except asyncio.CancelledError:
            if token.cancelled:
                token.raise_if_cancelled()
            raise
        finally:
            unlink()


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
    api_version: GraphAPIVersion | str = GraphAPIVersion.V1
    version_overrides: Mapping[str, GraphAPIVersion | str] = field(
        default_factory=lambda: dict(DEFAULT_VERSION_OVERRIDES),
    )
    page_size: int = 100
    enable_telemetry: bool = True
    telemetry_callback: Callable[[GraphTelemetryEvent], None] | None = None


class GraphClientFactory:
    def __init__(
        self, token_provider: TokenProvider, config: GraphClientConfig
    ) -> None:
        self._token_provider = token_provider
        self._config = config
        self._telemetry_callback = (
            config.telemetry_callback if config.enable_telemetry else None
        )
        self._default_api_version = _coerce_api_version(config.api_version)
        self._version_overrides: dict[str, str] = {}
        if config.version_overrides:
            for prefix, version in config.version_overrides.items():
                self.set_version_override(prefix, version)
        self._http_client: RateLimitedAsyncClient | None = None

    @property
    def default_api_version(self) -> str:
        """Return the currently configured default API version."""

        return self._default_api_version

    def set_default_api_version(self, version: GraphAPIVersion | str) -> None:
        """Update the default API version used when no overrides apply."""

        self._default_api_version = _coerce_api_version(version)

    @property
    def version_overrides(self) -> Mapping[str, str]:
        """Expose a copy of the registered path-based API version overrides."""

        return dict(self._version_overrides)

    def set_version_override(
        self,
        prefix: str,
        version: GraphAPIVersion | str,
    ) -> None:
        """Force a specific API version for requests matching a path prefix."""

        normalised = _normalise_override_key(prefix)
        if normalised != "/" and normalised.endswith("/"):
            normalised = normalised.rstrip("/")
        if not normalised or normalised == "":
            raise ValueError("Version override prefix cannot be empty")
        self._version_overrides[normalised] = _coerce_api_version(version)

    def remove_version_override(self, prefix: str) -> None:
        """Remove a previously registered API version override."""

        normalised = _normalise_override_key(prefix)
        if normalised != "/" and normalised.endswith("/"):
            normalised = normalised.rstrip("/")
        self._version_overrides.pop(normalised, None)

    def clear_version_overrides(self) -> None:
        """Clear all registered API version overrides."""

        self._version_overrides.clear()

    def resolve_api_version(
        self,
        path: str,
        *,
        explicit: ApiVersionInput = None,
    ) -> str:
        """Resolve the API version that will be used for a given request path."""

        relative, embedded = _prepare_relative_path(path)
        return self._resolve_api_version(relative, explicit or embedded)

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
        api_version: ApiVersionInput = None,
        cancellation_token: CancellationToken | None = None,
    ) -> httpx.Response:
        client = self._get_http_client()
        url = self._absolute_url(path, api_version=api_version)
        params_for_cli = dict(params) if params is not None else None
        try:
            response = await client._await_with_cancellation(  # type: ignore[attr-defined]
                client.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    data=data,
                    content=content,
                    headers=headers,
                ),
                cancellation_token,
            )
        except GraphAPIError as exc:
            self._enrich_graph_error(
                exc,
                method=method,
                url=url,
                params=params_for_cli,
                headers=headers,
                json_body=json_body,
                data=data,
                content=content,
            )
            raise
        return response

    async def request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        headers: dict[str, str] | None = None,
        api_version: ApiVersionInput = None,
        cancellation_token: CancellationToken | None = None,
    ) -> dict[str, Any]:
        response = await self.request(
            method,
            path,
            params=params,
            json_body=json_body,
            headers=headers,
            api_version=api_version,
            cancellation_token=cancellation_token,
        )
        return response.json()

    async def request_bytes(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        api_version: ApiVersionInput = None,
        cancellation_token: CancellationToken | None = None,
    ) -> bytes:
        response = await self.request(
            method,
            path,
            params=params,
            headers=headers,
            api_version=api_version,
            cancellation_token=cancellation_token,
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
        api_version: ApiVersionInput = None,
        cancellation_token: CancellationToken | None = None,
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
            if cancellation_token:
                cancellation_token.raise_if_cancelled()
            payload = await self.request_json(
                method,
                next_url,
                params=query,
                headers=headers,
                api_version=api_version if not next_url.startswith("http") else None,
                cancellation_token=cancellation_token,
            )
            value = payload.get("value")
            if isinstance(value, list):
                for item in value:
                    if cancellation_token:
                        cancellation_token.raise_if_cancelled()
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
        api_version: ApiVersionInput = None,
        cancellation_token: CancellationToken | None = None,
    ) -> dict[str, Any]:
        resolved_version: str | None = None
        if api_version is not None:
            resolved_version = _coerce_api_version(api_version)

        payload = {"requests": []}
        for index, request in enumerate(requests, start=1):
            explicit_version: ApiVersionInput = None
            request_path: str | None = None
            if isinstance(request, GraphRequest):
                explicit_version = request.api_version
                request_path = request.url
                entry = graph_request_to_batch_entry(
                    request,
                    request_id=str(index),
                )
            else:
                entry = dict(request)
                entry.setdefault("id", str(index))
                if entry.get("url") is None:
                    raise ValueError("Batch request entries must include a 'url'")
                url_value = entry.get("url")
                request_path = url_value if isinstance(url_value, str) else None
            payload["requests"].append(entry)

            if api_version is None and request_path:
                hint = self.resolve_api_version(request_path, explicit=explicit_version)
                if resolved_version is None:
                    resolved_version = hint
                elif resolved_version != hint:
                    raise ValueError(
                        "Batch requests span multiple Graph API versions; split the batch "
                        "by version or pass api_version explicitly.",
                    )

        if not payload["requests"]:
            return {"responses": []}

        effective_version = resolved_version or self._default_api_version

        return await self.request_json(
            "POST",
            "/$batch",
            json_body=payload,
            headers={"Content-Type": "application/json"},
            api_version=effective_version,
            cancellation_token=cancellation_token,
        )

    async def close(self) -> None:
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    # ------------------------------------------------------------- Internals

    def _enrich_graph_error(
        self,
        error: GraphAPIError,
        *,
        method: str,
        url: str,
        params: dict[str, Any] | None,
        headers: dict[str, str] | None,
        json_body: Any | None,
        data: Any | None,
        content: bytes | None,
    ) -> None:
        method_upper = method.upper()
        if params:
            query = str(httpx.QueryParams(params))
            if query:
                separator = "&" if "?" in url else "?"
                url = f"{url}{separator}{query}"

        error.request_method = method_upper
        error.request_url = url
        if not error.cli_example:
            error.cli_example = self._build_cli_example(
                method=method_upper,
                url=url,
                headers=headers,
                json_body=json_body,
                data=data,
                content=content,
            )

    def _build_cli_example(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str] | None,
        json_body: Any | None,
        data: Any | None,
        content: bytes | None,
    ) -> str:
        tokens: list[str] = ["az", "rest", "--method", method.upper(), "--url", url]
        for key, value in self._sanitize_headers(headers).items():
            tokens.extend(["--headers", f"{key}={value}"])
        body = self._serialise_body(json_body, data, content)
        if body is not None:
            tokens.extend(["--body", body])
        return shlex.join(tokens)

    @staticmethod
    def _sanitize_headers(headers: dict[str, str] | None) -> dict[str, str]:
        if not headers:
            return {}
        sanitized: dict[str, str] = {}
        for key, value in headers.items():
            if key.lower() == "authorization":
                continue
            sanitized[key] = str(value)
        return sanitized

    @staticmethod
    def _serialise_body(
        json_body: Any | None,
        data: Any | None,
        content: bytes | None,
    ) -> str | None:
        if json_body is not None:
            try:
                body_text = json.dumps(
                    json_body, ensure_ascii=True, separators=(",", ":")
                )
            except TypeError:
                body_text = repr(json_body)
            return GraphClientFactory._truncate_cli_value(body_text)
        if data is not None:
            if isinstance(data, (bytes, bytearray)):
                return "<binary data>"
            return GraphClientFactory._truncate_cli_value(str(data))
        if content is not None:
            return "<binary content>"
        return None

    @staticmethod
    def _truncate_cli_value(value: str, limit: int = 800) -> str:
        compact = value.replace("\n", " ").strip()
        if len(compact) <= limit:
            return compact
        return f"{compact[: limit - 3]}..."

    def _get_http_client(self) -> RateLimitedAsyncClient:
        if self._http_client is None:
            callback = self._telemetry_callback
            if callback is None and self._config.enable_telemetry:
                callback = self._default_telemetry_callback

            # Create auth callable that injects Bearer token into each request
            def bearer_auth(request: httpx.Request) -> httpx.Request:
                # Get token for configured Graph API scopes
                token = self._token_provider(self._config.scopes)
                request.headers["Authorization"] = f"Bearer {token.token}"
                return request

            self._http_client = RateLimitedAsyncClient(
                headers={"User-Agent": self._config.user_agent},
                auth=bearer_auth,
                telemetry_callback=callback,
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=60.0,
                    write=30.0,
                    pool=5.0,
                ),
            )
        return self._http_client

    def _resolve_api_version(
        self,
        relative_path: str,
        explicit: ApiVersionInput,
    ) -> str:
        if explicit is not None:
            return _coerce_api_version(explicit)
        override = self._lookup_override(relative_path)
        if override is not None:
            return override
        return self._default_api_version

    def _lookup_override(self, relative_path: str) -> str | None:
        best_prefix: str | None = None
        best_version: str | None = None
        for prefix, version in self._version_overrides.items():
            if _prefix_matches(prefix, relative_path):
                if best_prefix is None or len(prefix) > len(best_prefix):
                    best_prefix = prefix
                    best_version = version
        return best_version

    def _absolute_url(self, path: str, api_version: ApiVersionInput = None) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        relative, embedded = _prepare_relative_path(path)
        version = self._resolve_api_version(relative, api_version or embedded)
        return f"https://graph.microsoft.com/{version}{relative}"

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
    "GraphTelemetryEvent",
    "GraphAPIVersion",
    "ApiVersionInput",
]
