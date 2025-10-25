from __future__ import annotations

import base64
import json
from typing import Iterable, Sequence

from intune_manager.config.settings import DEFAULT_GRAPH_SCOPES


class PermissionChecker:
    """Evaluates granted scopes against required Intune permissions.

    Note: Microsoft returns scopes in the JWT token in short format (e.g., 'User.Read'),
    even when you request them in full URL format (e.g., 'https://graph.microsoft.com/User.Read').
    This class normalizes both required and granted scopes to short format for comparison.
    """

    def __init__(self, required_scopes: Sequence[str] | None = None) -> None:
        # Normalize required scopes to short format (remove Graph URL prefix)
        raw_scopes = required_scopes or DEFAULT_GRAPH_SCOPES
        self._required = set(self._normalize_scope(s) for s in raw_scopes)

    def missing_scopes(self, access_token: str) -> list[str]:
        """Return list of scopes that are required but not granted in the token.

        Returns scopes in short format (e.g., 'User.Read') regardless of how
        they were originally specified.
        """
        granted = set(
            self._normalize_scope(s) for s in self._extract_scopes(access_token)
        )
        missing = [scope for scope in self._required if scope not in granted]
        return missing

    def _normalize_scope(self, scope: str) -> str:
        """Normalize a scope to short format by removing the Graph URL prefix.

        Examples:
            'https://graph.microsoft.com/User.Read' -> 'User.Read'
            'User.Read' -> 'User.Read'
            'https://graph.microsoft.com/.default' -> '.default'
        """
        prefix = "https://graph.microsoft.com/"
        if scope.startswith(prefix):
            return scope[len(prefix) :]
        return scope

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
