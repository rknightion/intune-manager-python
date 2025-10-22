from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Iterable, List, Tuple


@dataclass(slots=True)
class StagedGroups:
    """Represents groups shared between modules for assignment workflows."""

    entries: List[Tuple[str, str]] = field(default_factory=list)
    timestamp: float = 0.0


_buffer = StagedGroups()


def stage_groups(groups: Iterable[Tuple[str, str]]) -> None:
    """Stage groups (id, display name) for consumption by the assignment centre."""

    unique: dict[str, str] = {}
    for group_id, display_name in groups:
        if not group_id:
            continue
        unique[group_id] = display_name or group_id

    _buffer.entries = [(group_id, unique[group_id]) for group_id in unique]
    _buffer.timestamp = time()


def consume_groups() -> StagedGroups:
    """Return the currently staged groups without clearing the buffer."""

    return StagedGroups(entries=list(_buffer.entries), timestamp=_buffer.timestamp)


def clear_groups() -> None:
    """Clear the staged groups buffer."""

    _buffer.entries.clear()
    _buffer.timestamp = time()


__all__ = ["stage_groups", "consume_groups", "clear_groups", "StagedGroups"]

