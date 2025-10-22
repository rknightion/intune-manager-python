from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Coroutine, Optional

from PySide6.QtCore import QObject, Signal
from qasync import QEventLoop


class AsyncBridge(QObject):
    task_completed = Signal(object, object)

    def __init__(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        super().__init__()
        self._loop = loop or asyncio.get_event_loop()

    def run_coroutine(self, coro: Awaitable[object]) -> None:
        asyncio.ensure_future(self._wrap(coro), loop=self._loop)

    async def _wrap(self, coro: Awaitable[object]) -> None:
        error = None
        result = None
        try:
            result = await coro
        except Exception as exc:  # noqa: BLE001
            error = exc
        self.task_completed.emit(result, error)


def ensure_qt_event_loop(
    loop: Optional[asyncio.AbstractEventLoop] = None,
) -> QEventLoop:
    existing = loop or asyncio.get_event_loop_policy().get_event_loop()
    if isinstance(existing, QEventLoop):
        return existing

    new_loop = QEventLoop(existing)
    asyncio.set_event_loop(new_loop)
    return new_loop


def run_in_qt(
    event_loop: Optional[QEventLoop], main_coro: Coroutine[object, object, object]
) -> None:
    loop = ensure_qt_event_loop(event_loop)
    loop.run_until_complete(main_coro)


def schedule_interval(
    callback: Callable[[], Awaitable[None]], *, seconds: float
) -> Callable[[], None]:
    loop = asyncio.get_event_loop()
    cancelled = False

    async def runner() -> None:
        while not cancelled:
            await callback()
            await asyncio.sleep(seconds)

    task = loop.create_task(runner())

    def cancel() -> None:
        nonlocal cancelled
        cancelled = True
        task.cancel()

    return cancel


def call_later(delay: float, func: Callable[[], None]) -> Callable[[], None]:
    loop = asyncio.get_event_loop()
    handler = loop.call_later(delay, func)
    return handler.cancel


__all__ = [
    "AsyncBridge",
    "ensure_qt_event_loop",
    "run_in_qt",
    "schedule_interval",
    "call_later",
]
