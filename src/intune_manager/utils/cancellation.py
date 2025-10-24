from __future__ import annotations

import asyncio
import logging
from typing import Callable


logger = logging.getLogger(__name__)


class CancellationError(asyncio.CancelledError):
    """Raised when an operation has been cancelled via a cancellation token."""

    def __init__(self, reason: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason


class _CancellationState:
    __slots__ = ("event", "reason", "callbacks", "tasks")

    def __init__(self) -> None:
        self.event = asyncio.Event()
        self.reason: str | None = None
        self.callbacks: list[Callable[["CancellationToken"], None]] = []
        self.tasks: set[asyncio.Task[object]] = set()


class CancellationToken:
    """Read-only handle that allows operations to observe cancellation requests."""

    __slots__ = ("_state",)

    def __init__(self, state: _CancellationState) -> None:
        self._state = state

    @property
    def cancelled(self) -> bool:
        return self._state.event.is_set()

    @property
    def reason(self) -> str | None:
        return self._state.reason

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise CancellationError(self._state.reason)

    async def wait(self) -> None:
        await self._state.event.wait()

    def on_cancel(self, callback: Callable[["CancellationToken"], None]) -> Callable[[], None]:
        if self.cancelled:
            callback(self)

            def noop() -> None:
                return None

            return noop

        self._state.callbacks.append(callback)

        def unsubscribe() -> None:
            try:
                self._state.callbacks.remove(callback)
            except ValueError:  # pragma: no cover - defensive cleanup
                pass

        return unsubscribe

    def link_task(self, task: asyncio.Task[object] | None = None) -> Callable[[], None]:
        target = task or asyncio.current_task()
        if target is None:  # pragma: no cover - should only occur in synchronous contexts
            raise RuntimeError("CancellationToken.link_task() must be called from within a running task")
        self._state.tasks.add(target)
        target.add_done_callback(self._state.tasks.discard)

        def unlink() -> None:
            self._state.tasks.discard(target)

        if self.cancelled:
            target.cancel()
        return unlink

    def __repr__(self) -> str:
        return f"CancellationToken(cancelled={self.cancelled}, reason={self.reason!r})"


class CancellationTokenSource:
    """Owns a cancellation token and triggers cancellation on request."""

    __slots__ = ("_state", "_token", "_linked_subscription")

    def __init__(self, *, linked_token: CancellationToken | None = None) -> None:
        self._state = _CancellationState()
        self._token = CancellationToken(self._state)
        self._linked_subscription: Callable[[], None] | None = None
        if linked_token is not None:
            self._linked_subscription = linked_token.on_cancel(lambda _token: self.cancel(reason=_token.reason))

    @property
    def token(self) -> CancellationToken:
        return self._token

    def cancel(self, *, reason: str | None = None) -> bool:
        if self._state.event.is_set():
            return False
        self._state.reason = reason
        self._state.event.set()
        error = CancellationError(reason)
        for callback in list(self._state.callbacks):
            try:
                callback(self._token)
            except Exception:  # pragma: no cover - error during cancellation notifications
                logger.exception("Cancellation callback raised an exception.")
        for task in list(self._state.tasks):
            task.cancel(error)
        return True

    def dispose(self) -> None:
        if self._linked_subscription is not None:
            try:
                self._linked_subscription()
            finally:
                self._linked_subscription = None

    def __enter__(self) -> CancellationToken:
        return self._token

    def __exit__(self, exc_type, exc, tb) -> None:
        self.dispose()


__all__ = ["CancellationError", "CancellationToken", "CancellationTokenSource"]
