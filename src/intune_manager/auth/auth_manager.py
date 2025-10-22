from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass
from typing import Sequence

import msal
from azure.core.credentials import AccessToken

from intune_manager.config.settings import DEFAULT_GRAPH_SCOPES, Settings
from intune_manager.graph.client import TokenProvider
from intune_manager.graph.errors import AuthenticationError
from intune_manager.utils import get_logger

from .token_cache import TokenCacheManager


logger = get_logger(__name__)


@dataclass(slots=True)
class AuthenticatedUser:
    display_name: str | None
    username: str | None
    home_account_id: str | None
    tenant_id: str | None


class AuthManager:
    """Centralized MSAL Public Client manager."""

    def __init__(self) -> None:
        self._cache_manager = TokenCacheManager()
        self._app: msal.PublicClientApplication | None = None
        self._settings: Settings | None = None
        self._lock = threading.RLock()
        self._user: AuthenticatedUser | None = None

    def configure(self, settings: Settings) -> None:
        if not settings.client_id:
            raise AuthenticationError(
                "Client ID must be provided before initializing authentication"
            )

        authority = settings.authority or settings.derive_authority()
        self._cache_manager = TokenCacheManager()
        self._app = msal.PublicClientApplication(
            client_id=settings.client_id,
            authority=authority,
            token_cache=self._cache_manager.cache,
        )
        self._settings = settings
        logger.info("Configured MSAL PublicClientApplication", authority=authority)

    def token_provider(self) -> TokenProvider:
        def provider(scopes: Sequence[str]) -> AccessToken:
            return self.acquire_token_sync(scopes)

        return provider

    async def acquire_token(self, scopes: Sequence[str] | None = None) -> AccessToken:
        scopes = list(scopes or DEFAULT_GRAPH_SCOPES)
        return await asyncio.to_thread(self._acquire_token_with_refresh, scopes, True)

    async def sign_in_interactive(
        self, scopes: Sequence[str] | None = None
    ) -> AccessToken:
        scopes = list(scopes or DEFAULT_GRAPH_SCOPES)
        return await asyncio.to_thread(self._acquire_token_interactive, scopes)

    async def sign_out(self) -> None:
        await asyncio.to_thread(self._sign_out_sync)

    def acquire_token_sync(self, scopes: Sequence[str] | None = None) -> AccessToken:
        scopes = list(scopes or DEFAULT_GRAPH_SCOPES)
        try:
            return self._acquire_token_with_refresh(scopes, interactive=False)
        except AuthenticationError as exc:
            raise AuthenticationError(
                "Interactive sign-in required before accessing Microsoft Graph",
            ) from exc

    def current_user(self) -> AuthenticatedUser | None:
        return self._user

    # Internal --------------------------------------------------------

    def _acquire_token_with_refresh(
        self,
        scopes: Sequence[str],
        interactive: bool,
    ) -> AccessToken:
        with self._lock:
            result = self._acquire_token_silent(scopes)
            if result is None:
                if not interactive:
                    raise AuthenticationError("Silent token acquisition failed")
                result = self._acquire_token_interactive(scopes)
            return result

    def _acquire_token_silent(self, scopes: Sequence[str]) -> AccessToken | None:
        app = self._ensure_app()
        account = self._get_account(app)
        if account is None:
            return None
        result = app.acquire_token_silent(list(scopes), account=account)
        if not result:
            return None
        token = self._process_result(result)
        self._cache_manager.save()
        return token

    def _acquire_token_interactive(self, scopes: Sequence[str]) -> AccessToken:
        app = self._ensure_app()
        result = app.acquire_token_interactive(
            scopes=list(scopes),
            prompt="select_account",
        )
        token = self._process_result(result)
        self._cache_manager.save()
        return token

    def _sign_out_sync(self) -> None:
        app = self._ensure_app()
        accounts = app.get_accounts()
        for account in accounts:
            app.remove_account(account)
        self._cache_manager.save()
        self._user = None
        logger.info("Signed out MSAL accounts")

    def _process_result(self, result: dict[str, object]) -> AccessToken:
        if "error" in result:
            raise AuthenticationError(
                message=f"MSAL error: {result.get('error_description', result['error'])}",
            )

        access_token = result.get("access_token")
        expires_on = result.get("expires_on") or result.get("expires_in")
        if not isinstance(access_token, str):
            raise AuthenticationError("MSAL response missing access token")

        expiry = (
            int(expires_on)
            if isinstance(expires_on, (int, str))
            else int(time.time()) + 3600
        )
        id_claims = result.get("id_token_claims")
        if isinstance(id_claims, dict):
            self._user = AuthenticatedUser(
                display_name=id_claims.get("name"),
                username=id_claims.get("preferred_username") or id_claims.get("email"),
                home_account_id=id_claims.get("oid"),
                tenant_id=id_claims.get("tid"),
            )

        return AccessToken(access_token, expiry)

    def _get_account(self, app: msal.PublicClientApplication) -> msal.Account | None:
        accounts = app.get_accounts()
        if accounts:
            account = accounts[0]
            self._user = AuthenticatedUser(
                display_name=account.get("name"),
                username=account.get("username"),
                home_account_id=account.get("home_account_id"),
                tenant_id=account.get("environment"),
            )
            return account
        return None

    def _ensure_app(self) -> msal.PublicClientApplication:
        if not self._app:
            raise AuthenticationError("Authentication has not been configured")
        return self._app


auth_manager = AuthManager()

__all__ = ["AuthManager", "AuthenticatedUser", "auth_manager"]
