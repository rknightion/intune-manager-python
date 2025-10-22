from __future__ import annotations

from pathlib import Path
from typing import Optional

import msal

from intune_manager.config.settings import runtime_dir


DEFAULT_CACHE_FILENAME = "msal_cache.bin"


class TokenCacheManager:
    """Handles persisting MSAL token cache to disk."""

    def __init__(self, cache_path: Optional[Path] = None) -> None:
        self._path = cache_path or runtime_dir() / DEFAULT_CACHE_FILENAME
        self._cache = msal.SerializableTokenCache()
        if self._path.exists():
            try:
                self._cache.deserialize(self._path.read_text(encoding="utf-8"))
            except Exception:  # pragma: no cover - corrupted cache
                self._cache = msal.SerializableTokenCache()

    @property
    def cache(self) -> msal.SerializableTokenCache:
        return self._cache

    @property
    def path(self) -> Path:
        return self._path

    def attach(self, app: msal.PublicClientApplication) -> None:
        app.token_cache = self._cache

    def save(self) -> None:
        if self._cache.has_state_changed:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(self._cache.serialize(), encoding="utf-8")


__all__ = ["TokenCacheManager", "DEFAULT_CACHE_FILENAME"]
