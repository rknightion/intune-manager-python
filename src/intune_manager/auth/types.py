"""Authentication type definitions."""

from __future__ import annotations

from typing import NamedTuple


class AccessToken(NamedTuple):
    """Represents an OAuth access token.

    Compatible with azure.core.credentials.AccessToken but avoids the dependency.
    """

    token: str
    """The token string."""

    expires_on: int
    """The token's expiration time in Unix time."""


__all__ = ["AccessToken"]
