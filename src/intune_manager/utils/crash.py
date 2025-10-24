from __future__ import annotations

import asyncio
import json
import platform
import sys
import threading
import traceback
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any

from intune_manager.config.settings import log_dir
from intune_manager.utils.logging import get_logger


class CrashReporter:
    """Capture unhandled exceptions and persist structured crash reports."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._directory = base_dir or log_dir()
        self._logger = get_logger(__name__)
        self._lock = threading.Lock()
        self._last_report: Path | None = None
        self._previous_hook = None
        self._previous_async_handler = None
        self._installed_loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------ Install

    def install(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Install hooks for global and asyncio exception handling."""

        if self._previous_hook is None:
            self._previous_hook = sys.excepthook
            sys.excepthook = self._handle_unhandled  # type: ignore[assignment]

        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

        if loop is not None and self._installed_loop is None:
            self._installed_loop = loop
            self._previous_async_handler = loop.get_exception_handler()
            loop.set_exception_handler(self._handle_async_exception)

    def uninstall(self) -> None:
        """Restore previous exception handlers (useful for tests)."""

        if self._previous_hook is not None:
            sys.excepthook = self._previous_hook  # type: ignore[assignment]
            self._previous_hook = None

        if self._installed_loop is not None:
            if self._previous_async_handler is not None:
                self._installed_loop.set_exception_handler(self._previous_async_handler)
            else:
                self._installed_loop.set_exception_handler(None)
            self._installed_loop = None
            self._previous_async_handler = None

    # --------------------------------------------------------------- Properties

    @property
    def last_report_path(self) -> Path | None:
        return self._last_report

    # -------------------------------------------------------------- Capture API

    def capture_exception(
        self,
        exc: BaseException,
        *,
        context: dict[str, Any] | None = None,
    ) -> Path:
        """Persist exception details to disk and log the incident."""

        exc_type = type(exc)
        tb = exc.__traceback__
        return self._record_exception(exc_type, exc, tb, context=context)

    # ----------------------------------------------------------- Handler internals

    def _handle_unhandled(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType | None,
    ) -> None:
        path = self._record_exception(exc_type, exc_value, exc_traceback)
        if self._previous_hook is not None:
            self._previous_hook(exc_type, exc_value, exc_traceback)
        else:  # pragma: no cover - defensive fallback
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
        self._logger.error(
            "Unhandled exception captured",
            crash_report=str(path),
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    def _handle_async_exception(
        self,
        loop: asyncio.AbstractEventLoop,
        context: dict[str, Any],
    ) -> None:
        exception = context.get("exception")
        report_context = {
            key: value
            for key, value in context.items()
            if key != "exception"
        }
        if exception is None:
            message = context.get("message") or "Unknown asyncio error"
            exception = RuntimeError(message)
        path = self.capture_exception(exception, context=report_context)
        if self._previous_async_handler is not None:
            self._previous_async_handler(loop, context)  # type: ignore[arg-type]
        else:
            loop.default_exception_handler(context)
        self._logger.error(
            "Asyncio exception captured",
            crash_report=str(path),
            context=report_context,
        )

    def _record_exception(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType | None,
        *,
        context: dict[str, Any] | None = None,
    ) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        with self._lock:
            self._directory.mkdir(parents=True, exist_ok=True)
            path = self._directory / f"crash-{timestamp}.log"
            trace = "".join(
                traceback.format_exception(exc_type, exc_value, exc_traceback)
            )
            metadata = {
                "timestamp": datetime.now(UTC).isoformat(),
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "executable": sys.executable,
                "args": sys.argv,
                "exception_type": exc_type.__name__,
            }
            if context:
                try:
                    metadata["asyncio_context"] = json.dumps(context, default=str)
                except TypeError:
                    metadata["asyncio_context"] = str(context)

            with path.open("w", encoding="utf-8") as handle:
                handle.write("Intune Manager Crash Report\n")
                handle.write("=" * 40 + "\n")
                json.dump(metadata, handle, indent=2)
                handle.write("\n\nTraceback:\n")
                handle.write(trace)

            self._last_report = path
            return path


__all__ = ["CrashReporter"]
