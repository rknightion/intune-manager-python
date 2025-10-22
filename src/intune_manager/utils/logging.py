from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, cast

import structlog
from loguru import logger as loguru_logger
from structlog.exceptions import DropEvent
from structlog.stdlib import BoundLogger
from structlog.typing import EventDict, WrappedLogger

from intune_manager.config.settings import log_dir


LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {message} | {extra}"
DEFAULT_LOG_FILENAME = "intune-manager.log"


@dataclass(slots=True)
class LoggingOptions:
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    debug: bool = False
    rotation: str = "10 MB"
    retention: str = "14 days"
    backtrace: bool = False
    diagnose: bool = False
    log_path: Optional[Path] = None


_configured_log_path: Optional[Path] = None
_is_configured = False


def configure_logging(options: LoggingOptions | None = None) -> Path:
    global _configured_log_path, _is_configured

    opts = options or LoggingOptions()

    console_level = "DEBUG" if opts.debug else opts.level
    log_path = opts.log_path or (log_dir() / DEFAULT_LOG_FILENAME)

    loguru_logger.remove()
    loguru_logger.add(
        sys.stderr,
        level=console_level,
        colorize=True,
        enqueue=True,
        backtrace=opts.backtrace or opts.debug,
        diagnose=opts.diagnose or opts.debug,
        format=LOG_FORMAT,
    )

    loguru_logger.add(
        log_path,
        level="DEBUG",
        rotation=opts.rotation,
        retention=opts.retention,
        enqueue=True,
        encoding="utf-8",
        format=LOG_FORMAT,
    )

    numeric_level = getattr(logging, opts.level.upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            _log_to_loguru,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        cache_logger_on_first_use=True,
    )

    _configured_log_path = log_path
    _is_configured = True
    return log_path


def _log_to_loguru(
    _: WrappedLogger,
    __: str,
    event_dict: EventDict,
) -> EventDict:
    level = str(event_dict.pop("level", "INFO")).upper()
    event = event_dict.pop("event", "")
    timestamp = event_dict.pop("timestamp", None)
    exception = event_dict.pop("exception", None)
    event_dict.pop("stack", None)
    bind_logger = loguru_logger.bind(**event_dict)
    if timestamp:
        bind_logger = bind_logger.bind(timestamp=timestamp)
    bind_logger.opt(depth=6, exception=exception).log(level, event)
    raise DropEvent


def get_logger(*initial_values: object, **initial_kw: object) -> BoundLogger:
    log = structlog.get_logger(*initial_values, **initial_kw)
    if not _is_configured:
        configure_logging()
    return cast(BoundLogger, log)


def log_file_path() -> Path:
    if _configured_log_path is None:
        return configure_logging()
    return _configured_log_path


__all__ = ["LoggingOptions", "configure_logging", "get_logger", "log_file_path"]
