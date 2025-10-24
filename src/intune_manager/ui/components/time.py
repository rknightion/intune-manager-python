from __future__ import annotations

from datetime import UTC, datetime, timedelta


def format_relative_timestamp(timestamp: datetime | None) -> str:
    """Return human-friendly description of time elapsed since timestamp."""

    if timestamp is None:
        return "never"
    reference = datetime.now(UTC)
    if timestamp.tzinfo is None:
        normalised = timestamp.replace(tzinfo=UTC)
    else:
        normalised = timestamp.astimezone(UTC)
    delta = reference - normalised
    if delta < timedelta(seconds=90):
        return "moments ago"
    minutes = delta.total_seconds() / 60
    if minutes < 90:
        count = max(int(minutes), 1)
        unit = "minute" if count == 1 else "minutes"
        return f"{count} {unit} ago"
    hours = minutes / 60
    if hours < 36:
        count = max(int(hours), 1)
        unit = "hour" if count == 1 else "hours"
        return f"{count} {unit} ago"
    return normalised.astimezone().strftime("%Y-%m-%d %H:%M")


__all__ = ["format_relative_timestamp"]
