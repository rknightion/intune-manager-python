from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass
from enum import Enum

try:  # pragma: no cover - optional dependency during tests
    import httpx  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - fallback when httpx missing
    httpx = None  # type: ignore[assignment]

from intune_manager.graph.errors import GraphAPIError, GraphErrorCategory


class ErrorSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(slots=True)
class ErrorDescriptor:
    headline: str
    detail: str
    severity: ErrorSeverity = ErrorSeverity.ERROR
    transient: bool = False
    suggestion: str | None = None


_NETWORK_ERRNOS = {
    getattr(socket, "EAI_AGAIN", None),
    getattr(socket, "EAI_FAIL", None),
    getattr(socket, "EAI_NONAME", None),
    getattr(socket, "EHOSTUNREACH", None),
    getattr(socket, "ENETDOWN", None),
    getattr(socket, "ENETUNREACH", None),
    getattr(socket, "ECONNREFUSED", None),
    getattr(socket, "ECONNRESET", None),
    getattr(socket, "ETIMEDOUT", None),
}
_NETWORK_ERRNOS.discard(None)


def describe_exception(error: Exception) -> ErrorDescriptor:
    descriptor = ErrorDescriptor(
        headline="Operation failed.",
        detail=f"{type(error).__name__}: {error}",
        severity=ErrorSeverity.ERROR,
        transient=False,
    )

    graph_error = _locate_graph_error(error)
    if graph_error is not None:
        descriptor.detail = _format_graph_detail(graph_error)
        descriptor.suggestion = graph_error.recovery_suggestion
        descriptor.transient = graph_error.is_retriable
        if graph_error.is_retriable:
            descriptor.severity = ErrorSeverity.WARNING
        descriptor.headline = _graph_headline(graph_error)
        return descriptor

    root = _unwrap_error(error)

    if _is_httpx_timeout(root):
        descriptor.headline = "Temporary timeout contacting Microsoft Graph."
        descriptor.detail = f"{type(root).__name__}: {root}"
        descriptor.severity = ErrorSeverity.WARNING
        descriptor.transient = True
        descriptor.suggestion = "Check your network connection and retry shortly."
        return descriptor

    if isinstance(root, asyncio.TimeoutError):
        descriptor.headline = "Operation timed out before Microsoft Graph responded."
        descriptor.detail = "asyncio.TimeoutError: Operation timed out"
        descriptor.severity = ErrorSeverity.WARNING
        descriptor.transient = True
        descriptor.suggestion = "Retry the request after verifying connectivity."
        return descriptor

    if isinstance(root, socket.gaierror):
        descriptor.headline = "DNS lookup failed while contacting Microsoft Graph."
        descriptor.detail = f"socket.gaierror: {root}"
        descriptor.severity = ErrorSeverity.WARNING
        descriptor.transient = True
        descriptor.suggestion = "Verify internet connectivity or DNS configuration."
        return descriptor

    if isinstance(root, OSError) and getattr(root, "errno", None) in _NETWORK_ERRNOS:
        descriptor.headline = "Network connection issue encountered."
        descriptor.detail = f"OSError[{root.errno}]: {root.strerror}"  # type: ignore[union-attr]
        descriptor.severity = ErrorSeverity.WARNING
        descriptor.transient = True
        descriptor.suggestion = "Retry once your connection is stable."
        return descriptor

    return descriptor


def _locate_graph_error(error: Exception) -> GraphAPIError | None:
    current: Exception | None = error
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(current, GraphAPIError):
            return current
        inner = getattr(current, "__cause__", None) or getattr(
            current, "__context__", None
        )
        if inner is None:
            break
        current = inner
    return None


def _unwrap_error(error: Exception) -> Exception:
    current = error
    visited: set[int] = set()
    while True:
        visited.add(id(current))
        inner = None
        if isinstance(current, GraphAPIError) and current.inner_error is not None:
            inner = current.inner_error
        elif getattr(current, "__cause__", None) is not None:
            inner = current.__cause__  # type: ignore[assignment]
        elif getattr(current, "__context__", None) is not None:
            inner = current.__context__  # type: ignore[assignment]
        if inner is None or id(inner) in visited:
            return current
        current = inner


def _graph_headline(error: GraphAPIError) -> str:
    match error.category:
        case GraphErrorCategory.RATE_LIMIT:
            return "Microsoft Graph throttled the request."
        case GraphErrorCategory.NETWORK:
            return "Network issue contacting Microsoft Graph."
        case GraphErrorCategory.AUTHENTICATION:
            return "Authentication is required to call Microsoft Graph."
        case GraphErrorCategory.PERMISSION:
            return "The signed-in account lacks required Graph permissions."
        case GraphErrorCategory.CONFLICT:
            return "The requested change conflicts with existing data."
        case GraphErrorCategory.VALIDATION:
            return "Microsoft Graph rejected the request payload."
        case _:
            return "Microsoft Graph request failed."


def _format_graph_detail(error: GraphAPIError) -> str:
    if error.code:
        return f"{error.code}: {error}"
    return str(error)


def _is_httpx_timeout(error: Exception | None) -> bool:
    if httpx is None:
        return False
    timeout_types: list[type[BaseException]] = []
    for name in [
        "TimeoutException",
        "ReadTimeout",
        "WriteTimeout",
        "PoolTimeout",
        "ConnectTimeout",
    ]:
        candidate = getattr(httpx, name, None)
        if isinstance(candidate, type) and issubclass(candidate, BaseException):
            timeout_types.append(candidate)
    return any(isinstance(error, timeout_type) for timeout_type in timeout_types)


__all__ = [
    "ErrorDescriptor",
    "ErrorSeverity",
    "describe_exception",
]
