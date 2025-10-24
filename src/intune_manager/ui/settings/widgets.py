from __future__ import annotations

import datetime as dt
from typing import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QPlainTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

from intune_manager.config import DEFAULT_GRAPH_SCOPES, Settings

from .setup_wizard import SetupWizard

from .controller import AuthStatus, SettingsController, SettingsSnapshot


def _format_scopes(scopes: Iterable[str]) -> str:
    return "\n".join(scopes)


class SettingsWidget(QWidget):
    """PySide6 widget for tenant + authentication configuration."""

    def __init__(
        self,
        controller: SettingsController | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller or SettingsController()
        self._secret_present = False
        self._clear_secret_requested = False

        self._build_ui()
        self._connect_signals()
        self._controller.load_settings()
        self._update_status(self._controller.current_status())

    # ------------------------------------------------------------------ UI setup

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.help_label = QLabel(
            (
                "Provide your Azure AD tenant ID and app registration details. "
                "Configure a public client redirect URI (e.g. http://localhost:8400) "
                "and grant the Intune-related Microsoft Graph **beta** scopes."
            ),
        )
        self.help_label.setWordWrap(True)
        self.help_label.setTextFormat(Qt.MarkdownText)

        layout.addWidget(self.help_label)

        layout.addWidget(self._build_tenant_group())
        layout.addWidget(self._build_scopes_group())
        layout.addWidget(self._build_actions_row())
        layout.addWidget(self._build_status_group())

        self.feedback_label = QLabel()
        self.feedback_label.setWordWrap(True)
        layout.addWidget(self.feedback_label)

        layout.addStretch()

    def _build_tenant_group(self) -> QGroupBox:
        group = QGroupBox("Azure AD registration")
        form = QFormLayout(group)

        self.tenant_input = QLineEdit()
        self.tenant_input.setPlaceholderText("directory (tenant) ID – GUID")

        self.client_input = QLineEdit()
        self.client_input.setPlaceholderText("application (client) ID – GUID")

        self.redirect_input = QLineEdit()
        self.redirect_input.setPlaceholderText("e.g. http://localhost:8400")

        self.authority_input = QLineEdit()
        self.authority_input.setPlaceholderText(
            "Optional override, defaults to https://login.microsoftonline.com/<tenant>"
        )

        self.client_secret_input = QLineEdit()
        self.client_secret_input.setEchoMode(QLineEdit.Password)

        self.client_secret_hint = QLabel()
        self.client_secret_hint.setWordWrap(True)
        self.client_secret_hint.setObjectName("clientSecretHint")

        self.clear_secret_button = QPushButton("Clear stored secret")
        self.clear_secret_button.setEnabled(False)
        self.clear_secret_button.clicked.connect(self._handle_clear_secret)

        form.addRow("Tenant ID", self.tenant_input)
        form.addRow("Client ID", self.client_input)
        form.addRow("Redirect URI", self.redirect_input)
        form.addRow("Authority", self.authority_input)
        form.addRow("Client Secret", self.client_secret_input)
        form.addRow("", self.client_secret_hint)
        form.addRow("", self.clear_secret_button)

        return group

    def _build_scopes_group(self) -> QGroupBox:
        group = QGroupBox("Microsoft Graph scopes")
        layout = QVBoxLayout(group)

        self.scopes_input = QPlainTextEdit()
        self.scopes_input.setPlaceholderText(_format_scopes(DEFAULT_GRAPH_SCOPES))
        self.scopes_input.setMinimumHeight(120)

        self.scope_hint = QLabel(
            "One scope per line. Leave empty to fall back to the recommended defaults.",
        )
        self.scope_hint.setWordWrap(True)

        layout.addWidget(self.scopes_input)
        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        self.copy_scopes_button = QToolButton()
        self.copy_scopes_button.setText("Copy scopes")
        self.copy_scopes_button.setToolTip(
            "Copy the configured scope list to the clipboard."
        )
        self.copy_scopes_button.clicked.connect(self._copy_configured_scopes)
        button_row.addWidget(self.copy_scopes_button)
        button_row.addStretch()
        layout.addLayout(button_row)
        layout.addWidget(self.scope_hint)
        return group

    def _build_actions_row(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        self.save_button = QPushButton("Save configuration")
        self.sign_in_button = QPushButton("Interactive sign-in")
        self.permission_button = QPushButton("Check permissions")
        self.connection_button = QPushButton("Test connection")
        self.setup_button = QPushButton("Setup wizard")
        self.reset_button = QPushButton("Reset configuration")

        layout.addWidget(self.save_button)
        layout.addWidget(self.sign_in_button)
        layout.addWidget(self.permission_button)
        layout.addWidget(self.connection_button)
        layout.addStretch()
        layout.addWidget(self.setup_button)
        layout.addWidget(self.reset_button)

        return container

    def _build_status_group(self) -> QGroupBox:
        group = QGroupBox("Authentication status")
        layout = QVBoxLayout(group)

        self.status_label = QLabel("Not signed in")
        self.status_label.setWordWrap(True)

        self.busy_label = QLabel()
        self.busy_label.setWordWrap(True)
        self.busy_label.setStyleSheet("color: #6c6c6c;")

        self.missing_scopes_label = QLabel("Missing scopes:")
        self.missing_scopes_label.setWordWrap(True)
        self.missing_scopes_label.setVisible(False)

        label_row = QHBoxLayout()
        label_row.setContentsMargins(0, 0, 0, 0)
        label_row.addWidget(self.missing_scopes_label)
        self.copy_missing_scopes_button = QToolButton()
        self.copy_missing_scopes_button.setText("Copy list")
        self.copy_missing_scopes_button.setToolTip(
            "Copy missing scopes to the clipboard."
        )
        self.copy_missing_scopes_button.clicked.connect(self._copy_missing_scopes)
        self.copy_missing_scopes_button.setEnabled(False)
        self.copy_missing_scopes_button.setVisible(False)
        label_row.addWidget(self.copy_missing_scopes_button)
        label_row.addStretch()

        self.missing_scopes_list = QListWidget()
        self.missing_scopes_list.setVisible(False)

        layout.addWidget(self.status_label)
        layout.addWidget(self.busy_label)
        layout.addLayout(label_row)
        layout.addWidget(self.missing_scopes_list)
        return group

    # ------------------------------------------------------------------ Signals

    def _connect_signals(self) -> None:
        self.save_button.clicked.connect(self._handle_save_clicked)
        self.sign_in_button.clicked.connect(self._handle_sign_in_clicked)
        self.permission_button.clicked.connect(self._handle_permissions_clicked)
        self.connection_button.clicked.connect(self._handle_connection_clicked)
        self.setup_button.clicked.connect(self.launch_setup_wizard)
        self.reset_button.clicked.connect(self._handle_reset_clicked)

        self._controller.settingsLoaded.connect(self._apply_settings)
        self._controller.settingsSaved.connect(self._apply_settings)
        self._controller.authStatusChanged.connect(self._update_status)
        self._controller.errorOccurred.connect(self._handle_error)
        self._controller.infoMessage.connect(self._handle_info)
        self._controller.busyStateChanged.connect(self._handle_busy_state)
        self._controller.testConnectionCompleted.connect(
            self._handle_test_connection_result
        )

    # ----------------------------------------------------------------- Handlers

    def _apply_settings(self, snapshot_obj: object) -> None:
        if not isinstance(snapshot_obj, SettingsSnapshot):
            return

        settings = snapshot_obj.settings
        self.tenant_input.setText(settings.tenant_id or "")
        self.client_input.setText(settings.client_id or "")
        self.redirect_input.setText(settings.redirect_uri or "")
        self.authority_input.setText(settings.authority or "")
        self.scopes_input.setPlainText(_format_scopes(settings.graph_scopes))

        self.client_secret_input.clear()
        self._secret_present = snapshot_obj.has_client_secret
        self._clear_secret_requested = False

        if self._secret_present:
            self.client_secret_input.setPlaceholderText(
                "Secret stored securely. Enter a new value to replace."
            )
            self.client_secret_hint.setText("Secret is stored in the OS keyring.")
        else:
            self.client_secret_input.setPlaceholderText("Optional client secret")
            self.client_secret_hint.setText(
                "Store confidential values in the OS keyring. Leave blank if not required."
            )
        self.clear_secret_button.setEnabled(self._secret_present)

    def _update_status(self, status_obj: object) -> None:
        if not isinstance(status_obj, AuthStatus):
            return

        if status_obj.username:
            expiry_text = ""
            if status_obj.expires_on:
                expiry = dt.datetime.fromtimestamp(status_obj.expires_on)
                expiry_text = f" • token expires {expiry:%Y-%m-%d %H:%M:%S}"

            self.status_label.setText(
                f"Signed in as {status_obj.display_name or status_obj.username}"
                f" ({status_obj.username}){expiry_text}"
            )
        else:
            self.status_label.setText("Not signed in.")

        self.missing_scopes_list.clear()
        missing = list(status_obj.missing_scopes or [])
        if missing:
            for scope in missing:
                QListWidgetItem(scope, self.missing_scopes_list)
        has_missing = bool(missing)
        self.missing_scopes_label.setVisible(has_missing)
        self.missing_scopes_list.setVisible(has_missing)
        self.copy_missing_scopes_button.setVisible(has_missing)
        self.copy_missing_scopes_button.setEnabled(has_missing)

    def _handle_save_clicked(self) -> None:
        settings = self._collect_settings()
        if settings is None:
            return
        secret, clear = self._gather_secret_inputs()
        self._controller.save_settings(
            settings, client_secret=secret, clear_secret=clear
        )

    def _handle_sign_in_clicked(self) -> None:
        settings = self._collect_settings(require_identifiers=True)
        if settings is None:
            return
        secret, clear = self._gather_secret_inputs()
        self._controller.save_settings(
            settings, client_secret=secret, clear_secret=clear
        )
        self._controller.test_sign_in(settings)

    def _handle_permissions_clicked(self) -> None:
        settings = self._collect_settings(require_identifiers=True)
        if settings is None:
            return
        self._controller.check_permissions(settings)

    def _handle_connection_clicked(self) -> None:
        settings = self._collect_settings(require_identifiers=True)
        if settings is None:
            return
        secret, clear = self._gather_secret_inputs()
        self._controller.save_settings(
            settings, client_secret=secret, clear_secret=clear
        )
        self._controller.test_graph_connection(settings)

    def _handle_reset_clicked(self) -> None:
        reply = QMessageBox.question(
            self,
            "Reset configuration",
            (
                "This will clear saved tenant settings, cached tokens, and stored secrets.\n"
                "Do you want to continue?"
            ),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._controller.reset_configuration()

    def _handle_clear_secret(self) -> None:
        if not self._secret_present:
            return
        reply = QMessageBox.question(
            self,
            "Clear stored secret",
            "Remove the stored secret from the system keyring?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._clear_secret_requested = True
            self.client_secret_input.clear()
            self.client_secret_input.setPlaceholderText(
                "Secret cleared. Enter to set again."
            )
            self.client_secret_hint.setText("Secret will be removed when you save.")
            self.clear_secret_button.setEnabled(False)

    def _handle_error(self, message: str) -> None:
        self._set_feedback(message, error=True)

    def _handle_info(self, message: str) -> None:
        self._set_feedback(message, error=False)

    def _handle_busy_state(self, busy: bool, message: str) -> None:
        for button in (
            self.save_button,
            self.sign_in_button,
            self.permission_button,
            self.connection_button,
            self.setup_button,
            self.reset_button,
        ):
            button.setDisabled(busy)
        self.busy_label.setText(message or "")

    # ---------------------------------------------------------------- Utilities

    def _copy_configured_scopes(self) -> None:
        scopes = self._parse_scopes(self.scopes_input.toPlainText())
        if not scopes:
            scopes = list(DEFAULT_GRAPH_SCOPES)
        QGuiApplication.clipboard().setText("\n".join(scopes))
        self._set_feedback(f"Copied {len(scopes)} scope(s) to clipboard.", error=False)

    def _copy_missing_scopes(self) -> None:
        count = self.missing_scopes_list.count()
        if count == 0:
            self._set_feedback("No missing scopes to copy.", error=True)
            return
        scopes = [self.missing_scopes_list.item(index).text() for index in range(count)]
        QGuiApplication.clipboard().setText("\n".join(scopes))
        self._set_feedback(
            f"Copied {count} missing scope(s) to clipboard.", error=False
        )

    def _collect_settings(self, require_identifiers: bool = False) -> Settings | None:
        tenant_id = self.tenant_input.text().strip() or None
        client_id = self.client_input.text().strip() or None
        redirect_uri = self.redirect_input.text().strip() or None
        authority = self.authority_input.text().strip() or None
        scopes_text = self.scopes_input.toPlainText().strip()

        scopes = self._parse_scopes(scopes_text)

        settings = Settings(
            tenant_id=tenant_id,
            client_id=client_id,
            redirect_uri=redirect_uri,
            authority=authority,
            graph_scopes=scopes,
        )

        if require_identifiers and (not tenant_id or not client_id):
            self._set_feedback("Tenant ID and Client ID are required.", error=True)
            return None

        return settings

    def _gather_secret_inputs(self) -> tuple[str | None, bool]:
        text = self.client_secret_input.text()
        if text:
            self._secret_present = True
            self._clear_secret_requested = False
            return text, False
        if self._clear_secret_requested:
            self._secret_present = False
            clear = True
        else:
            clear = False
        return None, clear

    def _handle_test_connection_result(self, success: bool, message: str) -> None:
        self._set_feedback(message, error=not success)

    def launch_setup_wizard(self) -> None:
        wizard = SetupWizard(self._controller, parent=self)
        wizard.exec()

    def _parse_scopes(self, text: str) -> list[str]:
        if not text:
            return list(DEFAULT_GRAPH_SCOPES)
        scopes: list[str] = []
        for line in text.replace(";", "\n").splitlines():
            scope = line.strip()
            if scope and scope not in scopes:
                scopes.append(scope)
        return scopes

    def _set_feedback(self, message: str, *, error: bool) -> None:
        if not message:
            self.feedback_label.clear()
            return
        if error:
            self.feedback_label.setStyleSheet("color: #c62828;")
        else:
            self.feedback_label.setStyleSheet("color: #1565c0;")
        self.feedback_label.setText(message)


__all__ = ["SettingsWidget"]
