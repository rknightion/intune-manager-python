from __future__ import annotations

import re
from typing import Final

_SEARCH_ALLOWED_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"[^0-9A-Za-z@\.\-\s_/+:]",
    flags=re.UNICODE,
)

_CONTROL_CHARS: Final[frozenset[str]] = frozenset(
    chr(code) for code in range(0x00, 0x20) if chr(code) not in {"\t", "\n"}
)


def sanitize_search_text(value: str) -> str:
    """Remove characters that could be used for SQL injection from search strings."""

    trimmed = value.strip()
    sanitized = _SEARCH_ALLOWED_PATTERN.sub("", trimmed)
    return sanitized


def sanitize_log_message(value: str) -> str:
    """Normalise log messages by stripping control characters and CR sequences."""

    normalised = value.replace("\r\n", "\n").replace("\r", "\n")
    return "".join(ch for ch in normalised if ch not in _CONTROL_CHARS)


__all__ = ["sanitize_search_text", "sanitize_log_message"]
