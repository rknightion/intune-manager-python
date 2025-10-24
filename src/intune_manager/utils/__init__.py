"""Shared utility helpers for Intune Manager."""

from .asyncio import (
    AsyncBridge,
    call_later,
    ensure_qt_event_loop,
    run_in_qt,
    schedule_interval,
)
from .background import BackgroundTask, run_background
from .cancellation import CancellationError, CancellationToken, CancellationTokenSource
from .logging import LoggingOptions, configure_logging, get_logger, log_file_path
from .crash import CrashReporter
from .sanitize import sanitize_log_message, sanitize_search_text
from .progress import (
    ProgressCallback,
    ProgressReporter,
    ProgressTracker,
    ProgressUpdate,
)

__all__ = [
    "LoggingOptions",
    "configure_logging",
    "get_logger",
    "log_file_path",
    "CrashReporter",
    "sanitize_search_text",
    "sanitize_log_message",
    "AsyncBridge",
    "ensure_qt_event_loop",
    "run_in_qt",
    "schedule_interval",
    "call_later",
    "BackgroundTask",
    "run_background",
    "CancellationToken",
    "CancellationTokenSource",
    "CancellationError",
    "ProgressUpdate",
    "ProgressTracker",
    "ProgressReporter",
    "ProgressCallback",
]
