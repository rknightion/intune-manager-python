from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Optional

from intune_manager.config.settings import runtime_dir


@dataclass(slots=True)
class _SafeModeState:
    enabled: bool = False
    reason: str | None = None
    purge_requested: bool = False


_STATE = _SafeModeState()


def _safe_mode_marker() -> Path:
    return runtime_dir() / "safe-mode-request.json"


def _cache_purge_marker() -> Path:
    return runtime_dir() / "cache-purge-request.json"


def _write_marker(path: Path, payload: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        # Best-effort persistence; failure should not crash the app.
        pass


def _read_marker(path: Path, *, consume: bool) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if consume:
            path.unlink(missing_ok=True)
        return payload
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        path.unlink(missing_ok=True)
        return None


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
    payload = {
        "reason": "runtime",
        "requested_at": datetime.now(UTC).isoformat(),
    }
    _write_marker(_cache_purge_marker(), payload)


def consume_cache_purge_request() -> bool:
    flag = _STATE.purge_requested
    _STATE.purge_requested = False
    marker = _cache_purge_marker()
    if marker.exists():
        marker.unlink(missing_ok=True)
        flag = True
    return flag


def schedule_safe_mode_request(reason: str | None = None) -> None:
    payload = {
        "reason": reason,
        "requested_at": datetime.now(UTC).isoformat(),
    }
    _write_marker(_safe_mode_marker(), payload)


def pending_safe_mode_request() -> dict[str, Any] | None:
    return _read_marker(_safe_mode_marker(), consume=False)


def consume_safe_mode_request_marker() -> dict[str, Any] | None:
    return _read_marker(_safe_mode_marker(), consume=True)


def cancel_safe_mode_request() -> None:
    _safe_mode_marker().unlink(missing_ok=True)


def schedule_cache_purge_request(reason: str | None = None) -> None:
    _STATE.purge_requested = True
    payload = {
        "reason": reason,
        "requested_at": datetime.now(UTC).isoformat(),
    }
    _write_marker(_cache_purge_marker(), payload)


def pending_cache_purge_request() -> dict[str, Any] | None:
    return _read_marker(_cache_purge_marker(), consume=False)


def cancel_cache_purge_request() -> None:
    _STATE.purge_requested = False
    _cache_purge_marker().unlink(missing_ok=True)


__all__ = [
    "enable_safe_mode",
    "disable_safe_mode",
    "safe_mode_enabled",
    "safe_mode_reason",
    "request_cache_purge",
    "consume_cache_purge_request",
    "schedule_safe_mode_request",
    "pending_safe_mode_request",
    "consume_safe_mode_request_marker",
    "cancel_safe_mode_request",
    "schedule_cache_purge_request",
    "pending_cache_purge_request",
    "cancel_cache_purge_request",
]
