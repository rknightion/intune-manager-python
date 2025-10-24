from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class _SafeModeState:
    enabled: bool = False
    reason: str | None = None
    purge_requested: bool = False


_STATE = _SafeModeState()


def enable_safe_mode(reason: str | None = None) -> None:
    _STATE.enabled = True
    _STATE.reason = reason


def disable_safe_mode() -> None:
    _STATE.enabled = False
    _STATE.reason = None
    _STATE.purge_requested = False


def safe_mode_enabled() -> bool:
    return _STATE.enabled


def safe_mode_reason() -> Optional[str]:
    return _STATE.reason


def request_cache_purge() -> None:
    _STATE.purge_requested = True


def consume_cache_purge_request() -> bool:
    flag = _STATE.purge_requested
    _STATE.purge_requested = False
    return flag


__all__ = [
    "enable_safe_mode",
    "disable_safe_mode",
    "safe_mode_enabled",
    "safe_mode_reason",
    "request_cache_purge",
    "consume_cache_purge_request",
]
