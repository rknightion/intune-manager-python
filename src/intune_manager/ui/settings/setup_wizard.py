from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
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
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from intune_manager.config import DEFAULT_GRAPH_SCOPES, Settings
from intune_manager.utils.sanitize import sanitize_log_message

from .controller import AuthStatus, SettingsController, SettingsSnapshot


@dataclass(slots=True)
class WizardContext:
    settings: Settings
    permissions_granted: bool = False
    test_passed: bool = False


class _WizardPage(QWizardPage):
    def __init__(
        self, wizard: "SetupWizard", *, title: str, subtitle: str | None = None
    ) -> None:
        super().__init__(wizard)
        self._wizard = wizard
        self.setTitle(title)
        if subtitle:
            self.setSubTitle(subtitle)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._layout.setSpacing(12)

        self.body = QVBoxLayout()
        self.body.setSpacing(12)
        self._layout.addLayout(self.body, stretch=1)

        self._busy_label = QLabel()
        self._busy_label.setWordWrap(True)
        self._busy_label.setStyleSheet("color: palette(mid);")
        self._busy_label.hide()
        self._layout.addWidget(self._busy_label)

        self._feedback_label = QLabel()
        self._feedback_label.setWordWrap(True)
        self._feedback_label.setTextFormat(Qt.TextFormat.PlainText)
        self._feedback_label.hide()
        self._layout.addWidget(self._feedback_label)

    def set_busy(self, busy: bool, message: str) -> None:
        if busy and message:
            self._busy_label.setText(message)
            self._busy_label.show()
        else:
            self._busy_label.hide()
            self._busy_label.clear()

    def set_feedback(self, message: str, *, error: bool) -> None:
        message = sanitize_log_message(message)
        if not message:
            self._feedback_label.hide()
            self._feedback_label.clear()
            return
        color = "#c62828" if error else "#1565c0"
        self._feedback_label.setStyleSheet(f"color: {color};")
        self._feedback_label.setText(message)
        self._feedback_label.show()

    @property
    def context(self) -> WizardContext:
        return self._wizard.context

    @property
    def controller(self) -> SettingsController:
        return self._wizard.controller


class _WelcomePage(_WizardPage):
    def __init__(self, wizard: "SetupWizard") -> None:
        super().__init__(
            wizard,
            title="Welcome",
            subtitle="This wizard will walk you through preparing Intune Manager for your tenant.",
        )

        intro = QLabel(
            (
                "<p>You'll need an Azure AD app registration configured as <strong>'Mobile and desktop applications'</strong> "
                "(public client) with the required Microsoft Graph scopes. We'll guide you through:</p>"
                "<ol>"
                "<li>Creating or locating your app registration</li>"
                "<li>Configuring it as a mobile/desktop app (not web app)</li>"
                "<li>Setting up the redirect URI</li>"
                "<li>Granting admin consent for Intune permissions</li>"
                "<li>Verifying connectivity to Microsoft Graph</li>"
                "</ol>"
                "<p><strong>Important:</strong> This application uses public client authentication and does NOT require "
                "a client secret. If your app is registered as a 'Web application', authentication will fail.</p>"
                "<p>Open the <a href='https://entra.microsoft.com/#view/Microsoft_AAD_IAM/ActiveDirectoryMenuBlade/~/RegisteredApps'>"  # noqa: E501
                "Azure portal – App registrations</a> in your browser so you can copy details as we go.</p>"
            ),
        )
        intro.setOpenExternalLinks(True)
        intro.setWordWrap(True)
        self.body.addWidget(intro)


class _ConfigurationPage(_WizardPage):
    def __init__(self, wizard: "SetupWizard") -> None:
        super().__init__(
            wizard,
            title="Tenant configuration",
            subtitle="Provide the identifiers for your Azure AD app registration.",
        )

        form_group = QGroupBox("Azure AD identifiers")
        form_layout = QFormLayout(form_group)

        self.tenant_input = QLineEdit()
        self.tenant_input.setFixedWidth(550)  # Fixed width - does not resize
        self.client_input = QLineEdit()
        self.client_input.setFixedWidth(550)  # Fixed width - does not resize
        self.redirect_input = QLineEdit()
        self.redirect_input.setFixedWidth(550)  # Fixed width - does not resize
        self.authority_input = QLineEdit()
        self.authority_input.setFixedWidth(550)  # Fixed width - does not resize

        self.registerField("tenant_id*", self.tenant_input)
        self.registerField("client_id*", self.client_input)
        self.registerField("redirect_uri", self.redirect_input)
        self.registerField("authority", self.authority_input)

        form_layout.addRow("Tenant ID", self.tenant_input)
        form_layout.addRow("Client ID", self.client_input)
        form_layout.addRow("Redirect URI", self.redirect_input)
        form_layout.addRow("Authority (optional)", self.authority_input)

        tool_row = QHBoxLayout()
        self.copy_redirect_button = QPushButton("Copy redirect URI")
        self.copy_scopes_button = QPushButton("Copy default scopes")
        self.portal_button = QPushButton("Open Azure portal")
        tool_row.addWidget(self.copy_redirect_button)
        tool_row.addWidget(self.copy_scopes_button)
        tool_row.addStretch()
        tool_row.addWidget(self.portal_button)

        self.body.addWidget(form_group)
        self.body.addLayout(tool_row)

        self.copy_redirect_button.clicked.connect(self._copy_redirect)
        self.copy_scopes_button.clicked.connect(self._copy_scopes)
        self.portal_button.clicked.connect(self._open_portal)

    def initializePage(self) -> None:
        snapshot = self.controller.load_settings()
        settings = snapshot.settings
        self.context.settings = settings

        self.tenant_input.setText(settings.tenant_id or "")
        self.client_input.setText(settings.client_id or "")
        self.redirect_input.setText(settings.redirect_uri or "http://localhost:8400")
        self.authority_input.setText(settings.authority or "")

    def validatePage(self) -> bool:
        tenant = self.tenant_input.text().strip()
        client = self.client_input.text().strip()
        if not tenant or not client:
            self.set_feedback("Tenant ID and Client ID are required.", error=True)
            return False

        redirect = self.redirect_input.text().strip() or "http://localhost:8400"
        authority = self.authority_input.text().strip() or None

        existing_scopes = self.context.settings.graph_scopes or list(
            DEFAULT_GRAPH_SCOPES
        )
        scopes = list(existing_scopes)
        settings = Settings(
            tenant_id=tenant,
            client_id=client,
            redirect_uri=redirect,
            authority=authority,
            graph_scopes=scopes,
        )

        self.context.settings = settings

        self.controller.save_settings(settings, client_secret=None, clear_secret=False)
        self.set_feedback("Settings saved.", error=False)
        return True

    def _copy_redirect(self) -> None:
        text = self.redirect_input.text().strip() or "http://localhost:8400"
        QGuiApplication.clipboard().setText(text)
        self.set_feedback(f"Copied redirect URI: {text}", error=False)

    def _copy_scopes(self) -> None:
        scopes_text = "\n".join(DEFAULT_GRAPH_SCOPES)
        QGuiApplication.clipboard().setText(scopes_text)
        self.set_feedback("Copied recommended Microsoft Graph scopes.", error=False)

    def _open_portal(self) -> None:
        QDesktopServices.openUrl(
            QUrl(
                "https://entra.microsoft.com/#view/Microsoft_AAD_IAM/ActiveDirectoryMenuBlade/~/RegisteredApps"
            ),
        )


class _PermissionsPage(_WizardPage):
    def __init__(self, wizard: "SetupWizard") -> None:
        super().__init__(
            wizard,
            title="Grant permissions",
            subtitle="Sign in and confirm that all required Microsoft Graph scopes are granted.",
        )

        self._status_label = QLabel("Not signed in.")
        self._status_label.setWordWrap(True)

        self._missing_list = QListWidget()
        self._missing_list.setVisible(False)

        button_row = QHBoxLayout()
        self.sign_in_button = QPushButton("Sign in")
        self.refresh_button = QPushButton("Refresh status")
        button_row.addWidget(self.sign_in_button)
        button_row.addWidget(self.refresh_button)
        button_row.addStretch()

        self.body.addWidget(self._status_label)
        self.body.addWidget(self._missing_list)
        self.body.addLayout(button_row)

        hint = QLabel(
            "Use an administrator account capable of granting consent for the Intune permissions.",
        )
        hint.setWordWrap(True)
        self.body.addWidget(hint)

        self.sign_in_button.clicked.connect(self._handle_sign_in)
        self.refresh_button.clicked.connect(self._handle_refresh)

        self._status_ok = False

    def initializePage(self) -> None:
        status = self.controller.current_status()
        self.update_status(status)

    def isComplete(self) -> bool:
        return self._status_ok

    def update_status(self, status: AuthStatus) -> None:
        if status.username:
            detail = status.display_name or status.username
            self._status_label.setText(
                f"Signed in as {detail} (tenant {status.tenant_id or 'unknown'})"
            )
        else:
            self._status_label.setText("Not signed in.")

        self._missing_list.clear()
        if status.missing_scopes:
            for scope in status.missing_scopes:
                QListWidgetItem(scope, self._missing_list)
            self._missing_list.setVisible(True)
            self.set_feedback(
                "Consent is still required for the listed scopes.",
                error=True,
            )
            self._status_ok = False
        else:
            self._missing_list.setVisible(False)
            if status.username:
                self.set_feedback("All required scopes granted.", error=False)
                self._status_ok = True
            else:
                self.set_feedback("Sign in to continue.", error=False)
                self._status_ok = False

        self.context.permissions_granted = self._status_ok
        self.completeChanged.emit()

    def _handle_sign_in(self) -> None:
        self.set_feedback("Launching sign-in…", error=False)
        self.controller.test_sign_in(self.context.settings)

    def _handle_refresh(self) -> None:
        self.set_feedback("Refreshing permissions…", error=False)
        self.controller.check_permissions(self.context.settings)


class _TestConnectionPage(_WizardPage):
    def __init__(self, wizard: "SetupWizard") -> None:
        super().__init__(
            wizard,
            title="Test connectivity",
            subtitle="Verify that Intune Manager can access Microsoft Graph.",
        )

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText('Click "Run test" to validate Graph access.')

        self.run_button = QPushButton("Run test")

        self.body.addWidget(self.log)
        self.body.addWidget(self.run_button, alignment=Qt.AlignmentFlag.AlignLeft)

        self.run_button.clicked.connect(self._handle_run)
        self._test_success = False

    def initializePage(self) -> None:
        self._test_success = False
        self.context.test_passed = False
        self.log.clear()
        self.set_feedback("", error=False)

    def isComplete(self) -> bool:
        return self._test_success

    def apply_result(self, success: bool, detail: str) -> None:
        detail = sanitize_log_message(detail)
        if success:
            self.log.appendPlainText(detail)
            self.set_feedback("Connectivity verified.", error=False)
            self._test_success = True
            self.context.test_passed = True
        else:
            self.log.appendPlainText(detail)
            self.set_feedback(detail, error=True)
            self._test_success = False
            self.context.test_passed = False
        self.completeChanged.emit()

    def _handle_run(self) -> None:
        self.log.clear()
        self.set_feedback("Starting connectivity test…", error=False)
        self.controller.test_graph_connection(self.context.settings)


class _CompletionPage(_WizardPage):
    def __init__(self, wizard: "SetupWizard") -> None:
        super().__init__(
            wizard,
            title="Setup complete",
            subtitle="Intune Manager is ready to use.",
        )
        summary = QLabel(
            (
                "You're signed in and Microsoft Graph access is verified."
                " Use the assignments, devices, and applications modules to begin managing your tenant."
            ),
        )
        summary.setWordWrap(True)
        self.body.addWidget(summary)
        self.setFinalPage(True)


class SetupWizard(QWizard):
    def __init__(self, controller: SettingsController, *, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        snapshot: SettingsSnapshot = controller.load_settings()
        self.context = WizardContext(settings=snapshot.settings)

        self.setWindowTitle("Intune Manager Setup Wizard")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)

        # Fixed size - non-resizable wizard window (700px wide, 700px tall)
        self.setFixedSize(700, 700)

        self._welcome_page = _WelcomePage(self)
        self._config_page = _ConfigurationPage(self)
        self._permissions_page = _PermissionsPage(self)
        self._test_page = _TestConnectionPage(self)
        self._completion_page = _CompletionPage(self)

        self.addPage(self._welcome_page)
        self.addPage(self._config_page)
        self.addPage(self._permissions_page)
        self.addPage(self._test_page)
        self.addPage(self._completion_page)

        self.controller.authStatusChanged.connect(self._handle_auth_status)
        self.controller.busyStateChanged.connect(self._handle_busy_state)
        self.controller.infoMessage.connect(self._handle_info)
        self.controller.errorOccurred.connect(self._handle_error)
        self.controller.testConnectionCompleted.connect(self._handle_test_completed)

    def _handle_auth_status(self, status_obj: object) -> None:
        if isinstance(status_obj, AuthStatus):
            self._permissions_page.update_status(status_obj)

    def _handle_busy_state(self, busy: bool, message: str) -> None:
        page = self.currentPage()
        if isinstance(page, _WizardPage):
            page.set_busy(busy, message)

    def _handle_info(self, message: str) -> None:
        page = self.currentPage()
        if isinstance(page, _WizardPage):
            page.set_feedback(message, error=False)

    def _handle_error(self, message: str) -> None:
        page = self.currentPage()
        if isinstance(page, _WizardPage):
            page.set_feedback(message, error=True)

    def _handle_test_completed(self, success: bool, detail: str) -> None:
        self._test_page.apply_result(success, detail)

    def reject(self) -> None:  # type: ignore[override]
        self._disconnect_signals()
        super().reject()

    def accept(self) -> None:  # type: ignore[override]
        self._disconnect_signals()
        super().accept()

    def _disconnect_signals(self) -> None:
        try:
            self.controller.authStatusChanged.disconnect(self._handle_auth_status)
            self.controller.busyStateChanged.disconnect(self._handle_busy_state)
            self.controller.infoMessage.disconnect(self._handle_info)
            self.controller.errorOccurred.disconnect(self._handle_error)
            self.controller.testConnectionCompleted.disconnect(
                self._handle_test_completed
            )
        except Exception:  # pragma: no cover - defensive
            pass


__all__ = ["SetupWizard"]
