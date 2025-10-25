from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass
from typing import Sequence

import msal

from intune_manager.auth.types import AccessToken
from intune_manager.config.settings import DEFAULT_GRAPH_SCOPES, Settings
from intune_manager.graph.client import TokenProvider
from intune_manager.graph.errors import AuthenticationError
from intune_manager.utils import get_logger

from .permission_checker import PermissionChecker

from .token_cache import TokenCacheManager


logger = get_logger(__name__)

# MSAL reserved scopes that cannot be explicitly requested with fully qualified URIs
_MSAL_RESERVED_SCOPES = frozenset({"profile", "openid", "offline_access"})


@dataclass(slots=True)
class AuthenticatedUser:
    display_name: str | None
    username: str | None
    home_account_id: str | None
    tenant_id: str | None


class AuthManager:
    """Centralized MSAL Public Client authentication manager.

    This manager uses MSAL PublicClientApplication for desktop/mobile app authentication.
    No client secret is required - authentication uses interactive browser-based flows.
    Your Azure AD app registration must be configured as "Mobile and desktop applications".
    """

    def __init__(self) -> None:
        self._cache_manager = TokenCacheManager()
        self._app: msal.PublicClientApplication | None = None
        self._settings: Settings | None = None
        self._lock = threading.RLock()
        self._user: AuthenticatedUser | None = None
        self._permission_checker = PermissionChecker()
        self._missing_scopes: list[str] = []

    def configure(self, settings: Settings) -> None:
        """Configure MSAL Public Client authentication.

        Args:
            settings: Application settings with tenant/client configuration

        Raises:
            AuthenticationError: If configuration fails or required parameters are missing

        Note:
            This uses PublicClientApplication which does not require a client secret.
            Your Azure AD app must be registered as "Mobile and desktop applications".
        """
        if not settings.client_id:
            raise AuthenticationError(
                "Client ID must be provided before initializing authentication"
            )

        authority = settings.authority or settings.derive_authority()
        self._cache_manager = TokenCacheManager(settings.token_cache_path)
        try:
            self._app = msal.PublicClientApplication(
                client_id=settings.client_id,
                authority=authority,
                token_cache=self._cache_manager.cache,
            )
        except ValueError as exc:
            logger.error(
                "Invalid MSAL configuration", authority=authority, error=str(exc)
            )
            raise AuthenticationError(
                f"Invalid authority or redirect URI: {exc}",
            ) from exc
        except Exception as exc:  # noqa: BLE001 - surface unexpected MSAL issues
            logger.exception("Failed to initialise MSAL client", authority=authority)
            raise AuthenticationError(
                f"Failed to initialize the MSAL client: {exc}",
            ) from exc
        self._settings = settings
        configured_scopes = list(settings.configured_scopes())
        self._permission_checker = PermissionChecker(configured_scopes or None)
        self._missing_scopes = []
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

    def missing_scopes(self) -> list[str]:
        """Return last-evaluated missing Graph scopes for the active token."""
        return list(self._missing_scopes)

    # Internal --------------------------------------------------------

    def _filter_scopes(self, scopes: Sequence[str]) -> list[str]:
        """
        Filter out MSAL reserved scopes and .default when mixed with specific scopes.

        MSAL automatically handles offline_access, profile, and openid.
        The .default scope should not be mixed with specific scopes.
        """
        filtered = [
            s
            for s in scopes
            if s not in _MSAL_RESERVED_SCOPES and not s.endswith("/.default")
        ]

        if len(filtered) != len(scopes):
            removed = set(scopes) - set(filtered)
            logger.debug(
                "Filtered reserved/incompatible scopes",
                removed=list(removed),
                remaining=filtered,
            )

        return filtered

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
        filtered_scopes = self._filter_scopes(scopes)
        result = app.acquire_token_silent(filtered_scopes, account=account)
        if not result:
            return None
        token = self._process_result(result)
        self._cache_manager.save()
        return token

    def _acquire_token_interactive(self, scopes: Sequence[str]) -> AccessToken:
        app = self._ensure_app()
        filtered_scopes = self._filter_scopes(scopes)
        result = app.acquire_token_interactive(
            scopes=filtered_scopes,
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
        self._cache_manager.clear()
        self._cache_manager.attach(app)
        self._user = None
        self._missing_scopes = []
        logger.info("Signed out MSAL accounts")

    def _process_result(self, result: dict[str, object]) -> AccessToken:
        if "error" in result:
            error_code = result.get("error")
            error_desc = result.get("error_description", error_code)

            # Check for common Azure AD app registration misconfiguration
            if (
                error_code == "AADSTS7000218"
                or "client_assertion" in str(error_desc).lower()
            ):
                raise AuthenticationError(
                    message=(
                        "Azure AD app registration type mismatch detected.\n\n"
                        "Your app is registered as a 'Web application' (confidential client), "
                        "but this desktop application uses public client authentication.\n\n"
                        "To fix this:\n"
                        "1. Go to Azure Portal > App registrations\n"
                        "2. Select your app registration\n"
                        "3. Under 'Authentication', configure as 'Mobile and desktop applications'\n"
                        "4. Add redirect URI: http://localhost:8400 (or your configured redirect URI)\n"
                        "5. Remove any 'Web' platform configurations\n\n"
                        f"Original error: {error_desc}"
                    ),
                )

            raise AuthenticationError(
                message=f"MSAL error: {error_desc}",
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

        self._missing_scopes = list(
            self._permission_checker.missing_scopes(access_token)
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
