from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

from intune_manager.utils import get_logger


logger = get_logger(__name__)

T_co = TypeVar("T_co", covariant=True)


class EventHook(Generic[T_co]):
    """Simple observer pattern helper for Qt-friendly bridging."""

    def __init__(self) -> None:
        self._subscribers: list[Callable[[T_co], None]] = []

    def subscribe(self, callback: Callable[[T_co], None]) -> Callable[[], None]:
        self._subscribers.append(callback)

        def unsubscribe() -> None:
            try:
                self._subscribers.remove(callback)
            except ValueError:  # pragma: no cover - best effort cleanup
                pass

        return unsubscribe

    def emit(self, payload: T_co) -> None:
        for callback in list(self._subscribers):
            try:
                callback(payload)
            except Exception:  # pragma: no cover - callbacks should not crash services
                logger.exception("Service event callback failed")


@dataclass(slots=True)
class RefreshEvent(Generic[T_co]):
    tenant_id: str | None
    items: T_co
    from_cache: bool


@dataclass(slots=True)
class ServiceErrorEvent:
    tenant_id: str | None
    error: Exception


__all__ = ["EventHook", "RefreshEvent", "ServiceErrorEvent"]
