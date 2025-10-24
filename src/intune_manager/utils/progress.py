from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Protocol


logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class ProgressUpdate:
    """Represents a snapshot of progress for long-running operations."""

    total: int | None
    completed: int
    failed: int
    current: str | None = None

    @property
    def remaining(self) -> int | None:
        if self.total is None:
            return None
        remaining = self.total - (self.completed + self.failed)
        return max(remaining, 0)

    @property
    def percent_complete(self) -> float | None:
        if not self.total:
            return None
        completed = max(self.completed, 0)
        total = max(self.total, 1)
        return min((completed / total) * 100, 100.0)


class ProgressReporter(Protocol):
    """Protocol describing callables that consume progress updates."""

    def __call__(self, update: ProgressUpdate) -> None: ...


class ProgressTracker:
    """Mutable helper that simplifies publishing `ProgressUpdate` snapshots."""

    __slots__ = ("_total", "_completed", "_failed", "_current", "_callback")

    def __init__(self, callback: ProgressReporter | None = None) -> None:
        self._total: int | None = None
        self._completed = 0
        self._failed = 0
        self._current: str | None = None
        self._callback = callback

    def bind(self, callback: ProgressReporter) -> None:
        self._callback = callback

    def start(
        self, *, total: int | None = None, current: str | None = None
    ) -> ProgressUpdate:
        self._total = total
        self._completed = 0
        self._failed = 0
        self._current = current
        return self._emit()

    def step(self, *, current: str | None = None) -> ProgressUpdate:
        if current is not None:
            self._current = current
        return self._emit()

    def succeeded(
        self, *, count: int = 1, current: str | None = None
    ) -> ProgressUpdate:
        self._completed += count
        if current is not None:
            self._current = current
        return self._emit()

    def failed(self, *, count: int = 1, current: str | None = None) -> ProgressUpdate:
        self._failed += count
        if current is not None:
            self._current = current
        return self._emit()

    def update_total(self, total: int | None) -> ProgressUpdate:
        self._total = total
        return self._emit()

    def finish(self) -> ProgressUpdate:
        return self._emit()

    def snapshot(self) -> ProgressUpdate:
        return ProgressUpdate(
            total=self._total,
            completed=self._completed,
            failed=self._failed,
            current=self._current,
        )

    def _emit(self) -> ProgressUpdate:
        update = self.snapshot()
        callback = self._callback
        if callback is not None:
            try:
                callback(update)
            except Exception:  # pragma: no cover - defensive: progress callbacks should not break operations
                logger.exception("Progress callback raised an exception.")
        return update


ProgressCallback = Callable[[ProgressUpdate], None]


__all__ = ["ProgressUpdate", "ProgressTracker", "ProgressReporter", "ProgressCallback"]
