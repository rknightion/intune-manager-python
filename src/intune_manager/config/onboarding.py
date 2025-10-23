from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from intune_manager.auth import TokenCacheManager

from .settings import Settings, SettingsManager


@dataclass(slots=True)
class FirstRunStatus:
    """Represents the application's initial setup state."""

    is_first_run: bool
    missing_settings: bool
    has_token_cache: bool
    token_cache_path: Path
    settings: Settings


def detect_first_run(
    *,
    settings_manager: SettingsManager | None = None,
    token_cache_manager: TokenCacheManager | None = None,
) -> FirstRunStatus:
    """Determine whether the app appears to be running for the first time."""

    manager = settings_manager or SettingsManager()
    settings = manager.load()
    cache_manager = token_cache_manager or TokenCacheManager()

    token_path = cache_manager.path
    has_token_cache = token_path.exists() and token_path.stat().st_size > 0
    missing_settings = not settings.is_configured
    is_first_run = missing_settings and not has_token_cache

    return FirstRunStatus(
        is_first_run=is_first_run,
        missing_settings=missing_settings,
        has_token_cache=has_token_cache,
        token_cache_path=token_path,
        settings=settings,
    )


__all__ = ["FirstRunStatus", "detect_first_run"]
