from __future__ import annotations

import asyncio
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal
from azure.core.credentials import AccessToken

from intune_manager.auth import (
    AuthManager,
    PermissionChecker,
    SecretStore,
    auth_manager,
)
from intune_manager.auth.auth_manager import AuthenticatedUser
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
        self._loop = ensure_qt_event_loop(loop)
        self._bridge = AsyncBridge(self._loop)
        self._bridge.task_completed.connect(self._handle_async_result)
        self._pending_action: str | None = None
        self._current_settings: Settings | None = None
        self._last_token: AccessToken | None = None

    # ------------------------------------------------------------------ Public

    def load_settings(self) -> SettingsSnapshot:
        settings = self._settings_manager.load()
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
            else:
                logger.info("Updated MSAL configuration", tenant=settings.tenant_id)
        else:
            logger.warning("Settings saved without mandatory identifiers")

        snapshot = SettingsSnapshot(settings=settings, has_client_secret=has_secret)
        self.settingsSaved.emit(snapshot)
        self.infoMessage.emit("Settings saved")

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

    # ----------------------------------------------------------------- Helpers

    def _configure_auth(self, settings: Settings) -> None:
        if not settings.client_id:
            raise AuthenticationError(
                "Client ID must be provided before authentication."
            )
        self._current_settings = settings
        self._auth.configure(settings)

    def _run_async(self, action: str, message: str, coro) -> None:
        if self._pending_action is not None:
            self.errorOccurred.emit("Another authentication task is already running.")
            return

        self._pending_action = action
        self._set_busy(True, message)
        self._bridge.run_coroutine(coro)

    def _handle_async_result(self, result: object, error: object) -> None:
        action = self._pending_action
        self._pending_action = None
        self._set_busy(False, "")

        if error:
            logger.error("Settings action failed", action=action, exception=error)
            self.errorOccurred.emit(str(error))
            return

        if not isinstance(result, AccessToken):
            logger.warning("Unexpected result for action %s: %r", action, result)
            return

        self._last_token = result
        status = self._build_status(result)

        if action == "sign_in":
            self.infoMessage.emit("Sign-in complete.")
        elif action == "check_permissions":
            self.infoMessage.emit("Permissions refreshed.")

        self.authStatusChanged.emit(status)

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
