from __future__ import annotations

from typing import Any


def enum_text(value: Any | None) -> str | None:
    """Return the string form of enums while tolerating plain strings."""

    if value is None:
        return None
    raw = getattr(value, "value", value)
    return str(raw)


__all__ = ["enum_text"]
