from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx

from PySide6.QtCore import QObject, Signal

from intune_manager.auth import (
    AuthManager,
    PermissionChecker,
    SecretStore,
    TokenCacheManager,
    auth_manager,
)
from intune_manager.auth.auth_manager import AuthenticatedUser
from intune_manager.auth.types import AccessToken
from intune_manager.config import Settings, SettingsManager
from intune_manager.graph.errors import AuthenticationError
from intune_manager.utils import get_logger
from intune_manager.utils.asyncio import AsyncBridge, ensure_qt_event_loop


logger = get_logger(__name__)

CLIENT_SECRET_KEY = "client_secret"


@dataclass(slots=True)
class SettingsSnapshot:
    settings: Settings
    has_client_secret: bool


@dataclass(slots=True)
class AuthStatus:
    display_name: str | None
    username: str | None
    tenant_id: str | None
    account_id: str | None
    expires_on: int | None
    missing_scopes: list[str]


class SettingsController(QObject):
    """Coordinates settings persistence and authentication checks for the UI."""

    settingsLoaded = Signal(object)
    settingsSaved = Signal(object)
    authStatusChanged = Signal(object)
    errorOccurred = Signal(str)
    busyStateChanged = Signal(bool, str)
    infoMessage = Signal(str)
    testConnectionCompleted = Signal(bool, str)

    def __init__(
        self,
        settings_manager: SettingsManager | None = None,
        auth: AuthManager | None = None,
        permission_checker: PermissionChecker | None = None,
        secret_store: SecretStore | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        super().__init__()
        self._settings_manager = settings_manager or SettingsManager()
        self._auth = auth or auth_manager
        self._permission_checker = permission_checker or PermissionChecker()
        self._secret_store = secret_store or SecretStore()
        self._token_cache_manager = TokenCacheManager()
        self._loop = ensure_qt_event_loop(loop)
        self._bridge = AsyncBridge(self._loop)
        self._bridge.task_completed.connect(self._handle_async_result)
        self._pending_action: str | None = None
        self._current_settings: Settings | None = None
        self._last_token: AccessToken | None = None

    # ------------------------------------------------------------------ Public

    def load_settings(self) -> SettingsSnapshot:
        settings = self._settings_manager.load()
        self._token_cache_manager = TokenCacheManager(settings.token_cache_path)
        has_secret = self._secret_store.get_secret(CLIENT_SECRET_KEY) is not None
        self._current_settings = settings
        snapshot = SettingsSnapshot(settings=settings, has_client_secret=has_secret)
        self.settingsLoaded.emit(snapshot)
        logger.debug("Loaded tenant settings", tenant=settings.tenant_id)
        return snapshot

    def save_settings(
        self,
        settings: Settings,
        *,
        client_secret: str | None,
        clear_secret: bool,
    ) -> None:
        settings.graph_scopes = list(settings.configured_scopes())
        self._settings_manager.save(settings)
        self._current_settings = settings
        self._token_cache_manager = TokenCacheManager(settings.token_cache_path)
        if clear_secret:
            self._secret_store.delete_secret(CLIENT_SECRET_KEY)
        elif client_secret:
            self._secret_store.set_secret(CLIENT_SECRET_KEY, client_secret)

        has_secret = self._secret_store.get_secret(CLIENT_SECRET_KEY) is not None

        if settings.is_configured:
            try:
                self._auth.configure(settings)
            except AuthenticationError as exc:
                logger.error("Failed to configure MSAL: %s", exc)
                self.errorOccurred.emit(str(exc))
            except Exception as exc:  # noqa: BLE001 - ensure UI feedback for unexpected failures
                logger.exception("Unexpected error during MSAL configuration")
                self.errorOccurred.emit(f"Failed to configure authentication: {exc}")
            else:
                logger.info("Updated MSAL configuration", tenant=settings.tenant_id)
        else:
            logger.warning("Settings saved without mandatory identifiers")

        snapshot = SettingsSnapshot(settings=settings, has_client_secret=has_secret)
        self.settingsSaved.emit(snapshot)
        self.infoMessage.emit("Settings saved")

    def current_settings(self) -> Settings:
        if self._current_settings is None:
            return self.load_settings().settings
        return self._current_settings

    def test_sign_in(self, settings: Settings) -> None:
        """Trigger an interactive login and update status/missing scopes."""
        try:
            self._configure_auth(settings)
        except AuthenticationError as exc:
            self.errorOccurred.emit(str(exc))
            return

        scopes = list(settings.configured_scopes())
        self._run_async(
            "sign_in",
            "Launching browser for sign-in…",
            self._auth.sign_in_interactive(scopes),
        )

    def check_permissions(self, settings: Settings) -> None:
        """Acquire token silently/refresh and report currently missing scopes."""
        try:
            self._configure_auth(settings)
        except AuthenticationError as exc:
            self.errorOccurred.emit(str(exc))
            return

        scopes = list(settings.configured_scopes())
        self._run_async(
            "check_permissions",
            "Evaluating Graph permissions…",
            self._auth.acquire_token(scopes),
        )

    def current_status(self) -> AuthStatus:
        """Return cached status without new token acquisition."""
        return self._build_status(self._last_token)

    def reset_configuration(self) -> None:
        """Clear persisted settings, secrets, and cached tokens."""

        try:
            empty = Settings()
            self._settings_manager.save(empty)
            self._current_settings = empty
            self._last_token = None
            try:
                self._secret_store.delete_secret(CLIENT_SECRET_KEY)
            except Exception:  # pragma: no cover - keyring best-effort
                logger.exception("Failed to delete stored client secret")

            try:
                self._token_cache_manager.clear()
            except Exception:  # pragma: no cover - filesystem best-effort
                logger.exception(
                    "Failed to securely clear token cache",
                    path=str(self._token_cache_manager.path),
                )
            self._token_cache_manager = TokenCacheManager(empty.token_cache_path)
            snapshot = SettingsSnapshot(settings=empty, has_client_secret=False)
            self.settingsLoaded.emit(snapshot)
            self.infoMessage.emit(
                "Configuration reset. Relaunch the setup wizard to configure Intune Manager.",
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Configuration reset failed")
            self.errorOccurred.emit(str(exc))

    def test_graph_connection(self, settings: Settings | None = None) -> None:
        """Run a lightweight Microsoft Graph query to validate connectivity."""

        target_settings = settings or self.current_settings()
        try:
            self._configure_auth(target_settings)
        except AuthenticationError as exc:
            self.errorOccurred.emit(str(exc))
            return

        scopes = list(target_settings.configured_scopes())
        self._run_async(
            "test_connection",
            "Testing Microsoft Graph connectivity…",
            self._perform_test_connection(scopes),
        )

    # ----------------------------------------------------------------- Helpers

    def _configure_auth(self, settings: Settings) -> None:
        if not settings.client_id:
            raise AuthenticationError(
                "Client ID must be provided before authentication."
            )
        self._current_settings = settings
        try:
            self._auth.configure(settings)
        except AuthenticationError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalise errors for UI handling
            logger.exception("Authentication configuration failed")
            raise AuthenticationError(str(exc)) from exc

    def _run_async(self, action: str, message: str, coro) -> None:
        if self._pending_action is not None:
            self.errorOccurred.emit("Another authentication task is already running.")
            return

        self._pending_action = action
        self._set_busy(True, message)
        self._bridge.run_coroutine(coro)

    async def _perform_test_connection(self, scopes: list[str]) -> tuple[bool, str]:
        try:
            token = await self._auth.acquire_token(scopes)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Token acquisition failed during connectivity test")
            return False, f"Unable to acquire token: {exc}"

        url = "https://graph.microsoft.com/v1.0/organization?$top=1"
        headers = {"Authorization": f"Bearer {token.token}"}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Graph connectivity test failed")
            return False, f"Graph API request failed: {exc}"

        return True, "Successfully queried Microsoft Graph organization endpoint."

    def _handle_async_result(self, result: object, error: object) -> None:
        action = self._pending_action
        self._pending_action = None
        self._set_busy(False, "")

        if action is None:
            logger.warning(
                "Async result received without pending action",
                result=result,
                error=error,
            )
            return

        if error:
            logger.error("Settings action failed", action=action, exception=error)
            if action == "test_connection":
                self.testConnectionCompleted.emit(False, str(error))
            self.errorOccurred.emit(str(error))
            return

        if action == "test_connection":
            if not isinstance(result, tuple) or len(result) != 2:
                logger.warning("Unexpected test connection result: %r", result)
                self.testConnectionCompleted.emit(
                    False, "Unexpected result from connectivity test."
                )
                return
            success, detail = bool(result[0]), str(result[1])
            if success:
                self.infoMessage.emit(detail)
            else:
                self.errorOccurred.emit(detail)
            self.testConnectionCompleted.emit(success, detail)
            return

        if not isinstance(result, AccessToken):
            logger.warning("Unexpected result for action %s: %r", action, result)
            return

        self._last_token = result
        status = self._build_status(result)

        self.authStatusChanged.emit(status)
        message: str | None = None
        if action == "sign_in":
            if status.missing_scopes:
                scopes = ", ".join(status.missing_scopes)
                message = (
                    "Sign-in succeeded, but the token is missing Microsoft Graph permissions: "
                    f"{scopes}. Grant these scopes to the Intune Manager app registration in Azure."
                )
            else:
                message = "Sign-in complete. All required Microsoft Graph permissions are present."
        elif action == "check_permissions":
            if status.missing_scopes:
                scopes = ", ".join(status.missing_scopes)
                message = (
                    "Permission check complete. The current token is missing Microsoft Graph permissions: "
                    f"{scopes}. Update the Azure app registration to grant these scopes."
                )
            else:
                message = "Permission check successful. Microsoft Graph permissions look good."

        if message:
            self.infoMessage.emit(message)

    def _set_busy(self, is_busy: bool, message: str) -> None:
        self.busyStateChanged.emit(is_busy, message)

    def _build_status(self, token: AccessToken | None) -> AuthStatus:
        user: AuthenticatedUser | None = self._auth.current_user()
        missing = self._determine_missing_scopes(token)
        return AuthStatus(
            display_name=user.display_name if user else None,
            username=user.username if user else None,
            tenant_id=user.tenant_id if user else None,
            account_id=user.home_account_id if user else None,
            expires_on=token.expires_on if token else None,
            missing_scopes=missing,
        )

    def _determine_missing_scopes(self, token: AccessToken | None) -> list[str]:
        if token is None:
            return []
        return list(self._permission_checker.missing_scopes(token.token))


__all__ = ["SettingsController", "SettingsSnapshot", "AuthStatus", "CLIENT_SECRET_KEY"]
