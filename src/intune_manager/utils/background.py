from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable


@dataclass(slots=True)
class BackgroundTask:
    task: asyncio.Task[Any]

    def cancel(self) -> None:
        self.task.cancel()


def run_background(coro: Awaitable[object]) -> BackgroundTask:
    loop = asyncio.get_event_loop()
    task = asyncio.ensure_future(coro, loop=loop)
    return BackgroundTask(task)


__all__ = ["BackgroundTask", "run_background"]
