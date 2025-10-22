from __future__ import annotations

import base64
import json
from typing import Iterable, Sequence

from intune_manager.config.settings import DEFAULT_GRAPH_SCOPES


class PermissionChecker:
    """Evaluates granted scopes against required Intune permissions."""

    def __init__(self, required_scopes: Sequence[str] | None = None) -> None:
        self._required = set(required_scopes or DEFAULT_GRAPH_SCOPES)

    def missing_scopes(self, access_token: str) -> list[str]:
        granted = set(self._extract_scopes(access_token))
        missing = [scope for scope in self._required if scope not in granted]
        return missing

    def _extract_scopes(self, token: str) -> Iterable[str]:
        try:
            parts = token.split(".")
            if len(parts) < 2:
                return []
            padding = "=" * (-len(parts[1]) % 4)
            payload = base64.urlsafe_b64decode(parts[1] + padding)
            claims = json.loads(payload)
            scopes = claims.get("scp") or claims.get("roles")
            if isinstance(scopes, str):
                return scopes.split()
            if isinstance(scopes, list):
                return scopes
        except Exception:  # pragma: no cover - decoding issues
            return []
        return []


__all__ = ["PermissionChecker"]
