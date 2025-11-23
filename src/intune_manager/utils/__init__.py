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
from .safe_mode import (
    cancel_cache_purge_request,
    cancel_safe_mode_request,
    consume_cache_purge_request,
    consume_safe_mode_request_marker,
    disable_safe_mode,
    enable_safe_mode,
    pending_cache_purge_request,
    pending_safe_mode_request,
    request_cache_purge,
    safe_mode_enabled,
    safe_mode_reason,
    schedule_cache_purge_request,
    schedule_safe_mode_request,
)
from .progress import (
    ProgressCallback,
    ProgressReporter,
    ProgressTracker,
    ProgressUpdate,
)
from .formatters import (
    format_file_size,
    format_license_count,
    format_architecture,
    format_min_os,
)

__all__ = [
    "LoggingOptions",
    "configure_logging",
    "get_logger",
    "log_file_path",
    "CrashReporter",
    "sanitize_search_text",
    "sanitize_log_message",
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
    "format_file_size",
    "format_license_count",
    "format_architecture",
    "format_min_os",
]
