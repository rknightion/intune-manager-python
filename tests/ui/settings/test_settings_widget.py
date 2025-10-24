from __future__ import annotations

import pytest
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QMessageBox

from intune_manager.config import Settings
from intune_manager.ui.settings.controller import AuthStatus, SettingsSnapshot
from intune_manager.ui.settings.widgets import SettingsWidget


class DummySettingsController(QObject):
    """Test double for SettingsController capturing method invocations."""

    settingsLoaded = Signal(object)
    settingsSaved = Signal(object)
    authStatusChanged = Signal(object)
    errorOccurred = Signal(str)
    infoMessage = Signal(str)
    busyStateChanged = Signal(bool, str)
    testConnectionCompleted = Signal(bool, str)

    def __init__(self) -> None:
        super().__init__()
        self._settings = Settings(
            tenant_id="contoso.onmicrosoft.com",
            client_id="00000000-0000-0000-0000-000000000000",
            redirect_uri="http://localhost:8400",
        )
        self._status = AuthStatus(
            display_name=None,
            username=None,
            tenant_id=None,
            account_id=None,
            expires_on=None,
            missing_scopes=[],
        )
        self.saved_settings: list[tuple[Settings, str | None, bool]] = []
        self.sign_in_calls: list[Settings] = []
        self.permission_checks: list[Settings] = []
        self.connection_checks: list[Settings] = []
        self.reset_invocations = 0

    def load_settings(self) -> SettingsSnapshot:
        snapshot = SettingsSnapshot(settings=self._settings, has_client_secret=False)
        self.settingsLoaded.emit(snapshot)
        return snapshot

    def save_settings(
        self,
        settings: Settings,
        *,
        client_secret: str | None,
        clear_secret: bool,
    ) -> None:
        self.saved_settings.append((settings, client_secret, clear_secret))
        snapshot = SettingsSnapshot(
            settings=settings,
            has_client_secret=bool(client_secret) and not clear_secret,
        )
        self.settingsSaved.emit(snapshot)

    def current_status(self) -> AuthStatus:
        return self._status

    def emit_status(self, status: AuthStatus) -> None:
        self._status = status
        self.authStatusChanged.emit(status)

    def test_sign_in(self, settings: Settings) -> None:
        self.sign_in_calls.append(settings)

    def check_permissions(self, settings: Settings) -> None:
        self.permission_checks.append(settings)

    def test_graph_connection(self, settings: Settings) -> None:
        self.connection_checks.append(settings)

    def reset_configuration(self) -> None:
        self.reset_invocations += 1


@pytest.fixture(autouse=True)
def auto_accept_dialogs(monkeypatch: pytest.MonkeyPatch):
    """Ensure QMessageBox interactions do not block automated UI tests."""

    monkeypatch.setattr(QMessageBox, "question", lambda *_, **__: QMessageBox.Yes)


def test_settings_widget_sign_in_flow(qtbot):
    controller = DummySettingsController()
    widget = SettingsWidget(controller=controller)
    qtbot.addWidget(widget)

    widget.tenant_input.setText("tenant-id")
    widget.client_input.setText("client-id")
    widget.redirect_input.setText("http://localhost:9000")
    widget.client_secret_input.setText("super-secret")

    qtbot.mouseClick(widget.sign_in_button, Qt.MouseButton.LeftButton)

    assert controller.saved_settings, "Expected save_settings to be invoked"
    saved_settings, secret, cleared = controller.saved_settings[-1]
    assert saved_settings.tenant_id == "tenant-id"
    assert saved_settings.client_id == "client-id"
    assert saved_settings.redirect_uri == "http://localhost:9000"
    assert secret == "super-secret"
    assert cleared is False

    assert controller.sign_in_calls, "Interactive sign-in should be triggered"
    assert controller.sign_in_calls[-1].tenant_id == "tenant-id"


def test_settings_widget_updates_status_and_missing_scopes(qtbot):
    controller = DummySettingsController()
    widget = SettingsWidget(controller=controller)
    qtbot.addWidget(widget)

    status = AuthStatus(
        display_name="Signed In User",
        username="user@contoso.com",
        tenant_id="tenant-id",
        account_id="account-id",
        expires_on=1700000000,
        missing_scopes=["Device.Read.All", "DeviceManagementApps.Read.All"],
    )
    controller.emit_status(status)

    assert "Signed In User" in widget.status_label.text()
    assert widget.missing_scopes_list.count() == 2
    assert widget.copy_missing_scopes_button.isEnabled()

