from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from functools import partial

from intune_manager.data.repositories.base import DEFAULT_SCOPE
from intune_manager.services import DiagnosticsService, ServiceRegistry
from intune_manager.utils import AsyncBridge
from intune_manager.utils.safe_mode import (
    cancel_cache_purge_request,
    cancel_safe_mode_request,
    pending_cache_purge_request,
    pending_safe_mode_request,
    schedule_cache_purge_request,
    schedule_safe_mode_request,
)
from intune_manager.ui.settings.widgets import SettingsWidget


@dataclass(slots=True)
class CacheSeverityStyle:
    label: str
    color: str


SEVERITY_STYLES: dict[str, CacheSeverityStyle] = {
    "info": CacheSeverityStyle("Healthy", "#1b8651"),
    "warning": CacheSeverityStyle("Needs attention", "#c15d12"),
    "error": CacheSeverityStyle("Action required", "#c92a2a"),
}


class SettingsPage(QWidget):
    """Container widget hosting settings configuration and diagnostics tabs."""

    def __init__(
        self,
        *,
        diagnostics: DiagnosticsService | None,
        services: ServiceRegistry | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._diagnostics = diagnostics
        self._services = services
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()
        tabs.setTabPosition(QTabWidget.West)
        tabs.setDocumentMode(True)
        layout.addWidget(tabs)

        self._settings_tab = SettingsWidget(parent=self)
        tabs.addTab(self._settings_tab, "Configuration")

        about_tab = AboutWidget(diagnostics=self._diagnostics, parent=self)

        if self._diagnostics is not None:
            self._cache_tab = CacheManagementWidget(
                self._diagnostics,
                services=self._services,
                parent=self,
            )
            tabs.addTab(self._cache_tab, "Cache & Storage")

            self._diagnostics_tab = DiagnosticsWidget(self._diagnostics, parent=self)
            self._diagnostics_tab.telemetryChanged.connect(about_tab.refresh)
            tabs.addTab(self._diagnostics_tab, "Diagnostics")
        else:
            placeholder = QLabel(
                "Diagnostics services are unavailable. Configure authentication first.",
            )
            placeholder.setWordWrap(True)
            placeholder.setAlignment(Qt.AlignCenter)
            tabs.addTab(placeholder, "Diagnostics")

        tabs.addTab(about_tab, "About & Appearance")

    def launch_setup_wizard(self) -> None:
        self._settings_tab.launch_setup_wizard()


class CacheManagementWidget(QWidget):
    """Provide cache inspection, repair, and attachment management controls."""

    def __init__(
        self,
        diagnostics: DiagnosticsService,
        *,
        services: ServiceRegistry | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._diagnostics = diagnostics
        self._services = services
        self._bridge: AsyncBridge | None = (
            AsyncBridge() if services is not None else None
        )
        if self._bridge is not None:
            self._bridge.task_completed.connect(self._handle_async_completed)
        self._pending_refresh: tuple[str, str | None] | None = None
        self._latest_report = diagnostics.last_cache_report()
        self._build_ui()
        self._refresh_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        status_group = QGroupBox("Cache health")
        status_layout = QHBoxLayout(status_group)
        status_layout.setContentsMargins(12, 12, 12, 12)
        self._status_label = QLabel("No inspection run yet")
        self._status_label.setObjectName("CacheStatusLabel")
        status_layout.addWidget(self._status_label)
        status_layout.addStretch()

        self._inspect_button = QPushButton("Inspect & repair cache")
        self._inspect_button.clicked.connect(self._run_inspection)
        status_layout.addWidget(self._inspect_button)

        layout.addWidget(status_group)

        self._table = QTableWidget(0, 9)
        self._table.setHorizontalHeaderLabels(
            [
                "Resource",
                "Scope",
                "Last Refresh",
                "Expires",
                "Recorded",
                "Actual",
                "Repaired",
                "Issues",
                "Actions",
            ],
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionMode(QTableWidget.NoSelection)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self._table)

        attachment_group = QGroupBox("Attachment cache")
        attachment_layout = QHBoxLayout(attachment_group)
        attachment_layout.setContentsMargins(12, 12, 12, 12)
        self._attachment_label = QLabel()
        attachment_layout.addWidget(self._attachment_label)
        attachment_layout.addStretch()
        self._purge_button = QPushButton("Purge attachments")
        self._purge_button.clicked.connect(self._purge_attachments)
        attachment_layout.addWidget(self._purge_button)
        layout.addWidget(attachment_group)

        action_row = QHBoxLayout()
        action_row.addStretch()
        self._clear_button = QPushButton("Clear all cached data")
        self._clear_button.clicked.connect(self._clear_all)
        action_row.addWidget(self._clear_button)
        layout.addLayout(action_row)

        layout.addStretch()

    def _run_inspection(self) -> None:
        reply = QMessageBox.question(
            self,
            "Inspect cache",
            ("Run cache validation now? This may purge invalid records automatically."),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        report = self._diagnostics.inspect_cache(auto_repair=True)
        self._latest_report = report
        self._refresh_ui()
        QMessageBox.information(
            self,
            "Inspection complete",
            f"Inspection finished with status: {report.severity.value.upper()}",
        )

    def _clear_all(self) -> None:
        reply = QMessageBox.question(
            self,
            "Clear cached data",
            "Remove all cached Graph data for the current profile?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._diagnostics.clear_all_caches()
        QMessageBox.information(self, "Cache cleared", "Cached data removed.")
        self._latest_report = None
        self._refresh_ui()

    def _purge_attachments(self) -> None:
        reply = QMessageBox.question(
            self,
            "Purge attachments",
            "Delete all downloaded icons and attachments?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._diagnostics.purge_attachments()
        QMessageBox.information(self, "Attachments purged", "Binary cache cleared.")
        self._update_attachment_stats()

    def _refresh_ui(self) -> None:
        if self._latest_report is not None:
            severity_key = self._latest_report.severity.value
            style = SEVERITY_STYLES.get(
                severity_key, CacheSeverityStyle("Unknown", "#5f6673")
            )
            self._status_label.setText(style.label)
            self._status_label.setStyleSheet(f"color: {style.color}; font-weight: 600;")
            self._populate_table(self._latest_report.entries)
        else:
            self._status_label.setText("No inspection run yet")
            self._status_label.setStyleSheet("color: #5f6673;")
            self._table.setRowCount(0)
        self._update_attachment_stats()

    def _populate_table(self, entries: Iterable) -> None:
        self._table.setRowCount(0)
        for entry in entries:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(entry.resource))
            scope_display = entry.scope if entry.scope != DEFAULT_SCOPE else "default"
            self._table.setItem(row, 1, QTableWidgetItem(scope_display))
            if entry.last_refresh is not None:
                last_refresh = entry.last_refresh.strftime("%Y-%m-%d %H:%M:%S")
            else:
                last_refresh = "—"
            self._table.setItem(row, 2, QTableWidgetItem(last_refresh))
            if entry.expires_at is not None:
                expires = entry.expires_at.strftime("%Y-%m-%d %H:%M:%S")
            else:
                expires = "—"
            self._table.setItem(row, 3, QTableWidgetItem(expires))
            recorded = (
                "–" if entry.recorded_count is None else str(entry.recorded_count)
            )
            self._table.setItem(row, 4, QTableWidgetItem(recorded))
            self._table.setItem(row, 5, QTableWidgetItem(str(entry.actual_count)))
            repaired_text = "Yes" if entry.repaired else "No"
            self._table.setItem(row, 6, QTableWidgetItem(repaired_text))
            issue_lines = [
                f"[{issue.severity.value.upper()}] {issue.message}"
                for issue in entry.issues
            ]
            issue_text = "\n".join(issue_lines)
            self._table.setItem(row, 7, QTableWidgetItem(issue_text))
            if self._services is not None and self._bridge is not None:
                button = QPushButton("Refresh…")
                available = self._service_available(entry.resource)
                button.setEnabled(available)
                button.setProperty("cache_refresh_available", available)
                if available:
                    button.clicked.connect(
                        partial(
                            self._handle_refresh_clicked,
                            entry.resource,
                            entry.tenant_id,
                        ),
                    )
                else:
                    button.setToolTip("Refresh service not available in this session.")
                self._table.setCellWidget(row, 8, button)
            else:
                placeholder = QLabel("—")
                placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setCellWidget(row, 8, placeholder)
        self._table.resizeColumnsToContents()

    def _update_attachment_stats(self) -> None:
        stats = self._diagnostics.attachment_stats()
        formatted_size = self._format_bytes(stats.total_bytes)
        if stats.last_modified is not None:
            accessed = stats.last_modified.strftime("%Y-%m-%d %H:%M:%S")
        else:
            accessed = "N/A"
        self._attachment_label.setText(
            f"Cached files: {stats.total_files} • Size: {formatted_size} • Last accessed: {accessed}"
        )

    def _format_bytes(self, value: int) -> str:
        if value < 1024:
            return f"{value} B"
        units = ["KiB", "MiB", "GiB", "TiB"]
        size = float(value)
        for unit in units:
            size /= 1024.0
            if size < 1024.0:
                return f"{size:.2f} {unit}"
        return f"{size:.2f} PiB"

    def _service_available(self, resource: str) -> bool:
        return self._resolve_service(resource) is not None

    def _resolve_service(self, resource: str):  # noqa: ANN001 - dynamic return
        if self._services is None:
            return None
        mapping = {
            "devices": "devices",
            "mobile_apps": "applications",
            "groups": "groups",
            "configuration_profiles": "configurations",
            "audit_events": "audit",
            "assignment_filters": "assignment_filters",
        }
        attr = mapping.get(resource)
        if not attr:
            return None
        return getattr(self._services, attr, None)

    def _handle_refresh_clicked(self, resource: str, tenant_id: str | None) -> None:
        if self._bridge is None or self._services is None:
            QMessageBox.information(
                self,
                "Refresh unavailable",
                "No active services are available to refresh this cache.",
            )
            return
        if not self._service_available(resource):
            QMessageBox.information(
                self,
                "Service unavailable",
                "The corresponding service is not configured in this session.",
            )
            return
        if self._pending_refresh is not None:
            return
        self._pending_refresh = (resource, tenant_id)
        friendly = resource.replace("_", " ").title()
        self._status_label.setText(f"Refreshing {friendly} cache…")
        self._set_controls_enabled(False)
        self._bridge.run_coroutine(self._refresh_resource_async(resource, tenant_id))

    async def _refresh_resource_async(
        self, resource: str, tenant_id: str | None
    ) -> str:
        service = self._resolve_service(resource)
        if service is None:
            raise RuntimeError("Service not configured")
        await service.refresh(tenant_id=tenant_id, force=True)
        return resource

    def _handle_async_completed(self, result: object, error: object) -> None:
        if self._pending_refresh is None:
            return
        resource, _tenant_id = self._pending_refresh
        self._pending_refresh = None
        self._set_controls_enabled(True)
        if error:
            QMessageBox.critical(
                self,
                "Refresh failed",
                f"Failed to refresh {resource.replace('_', ' ')} cache: {error}",
            )
            self._refresh_ui()
            return
        try:
            self._latest_report = self._diagnostics.inspect_cache(auto_repair=True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self,
                "Inspection warning",
                f"Cache refreshed but inspection failed: {exc}",
            )
        else:
            QMessageBox.information(
                self,
                "Cache refreshed",
                f"Updated {resource.replace('_', ' ')} cache from Microsoft Graph.",
            )
        self._refresh_ui()

    def _set_controls_enabled(self, enabled: bool) -> None:
        for button in [self._inspect_button, self._purge_button, self._clear_button]:
            button.setEnabled(enabled)
        for row in range(self._table.rowCount()):
            widget = self._table.cellWidget(row, 8)
            if isinstance(widget, QPushButton):
                available = bool(widget.property("cache_refresh_available"))
                widget.setEnabled(enabled and available)


class DiagnosticsWidget(QWidget):
    """Expose log export, keyring status, and telemetry preferences."""

    telemetryChanged = Signal(bool)

    def __init__(
        self, diagnostics: DiagnosticsService, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._diagnostics = diagnostics
        self._build_ui()
        self._refresh_logs()
        self._refresh_keyring()
        self._apply_telemetry_state()
        self._refresh_recovery_status()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        log_group = QGroupBox("Application logs")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(12, 12, 12, 12)

        self._log_list = QListWidget()
        self._log_list.setSelectionMode(QListWidget.SingleSelection)
        log_layout.addWidget(self._log_list)

        log_buttons = QHBoxLayout()
        refresh_logs = QPushButton("Refresh")
        refresh_logs.clicked.connect(self._refresh_logs)
        log_buttons.addWidget(refresh_logs)

        open_folder = QPushButton("Open folder")
        open_folder.clicked.connect(self._open_log_folder)
        log_buttons.addWidget(open_folder)

        export_button = QPushButton("Export bundle…")
        export_button.clicked.connect(self._export_logs)
        log_buttons.addWidget(export_button)
        log_buttons.addStretch()

        log_layout.addLayout(log_buttons)
        layout.addWidget(log_group)

        keyring_group = QGroupBox("Keyring status")
        keyring_layout = QHBoxLayout(keyring_group)
        keyring_layout.setContentsMargins(12, 12, 12, 12)
        self._keyring_label = QLabel()
        self._keyring_label.setWordWrap(True)
        keyring_layout.addWidget(self._keyring_label)
        keyring_layout.addStretch()
        layout.addWidget(keyring_group)

        telemetry_group = QGroupBox("Telemetry")
        telemetry_layout = QVBoxLayout(telemetry_group)
        telemetry_layout.setContentsMargins(12, 12, 12, 12)
        self._telemetry_toggle = QCheckBox(
            "Share anonymised diagnostics to improve Intune Manager"
        )
        self._telemetry_toggle.toggled.connect(self._handle_telemetry_toggled)
        telemetry_layout.addWidget(self._telemetry_toggle)
        hint = QLabel(
            "Telemetry never includes tenant IDs or personal information. Toggle to help improve reliability.",
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #5f6673;")
        telemetry_layout.addWidget(hint)
        layout.addWidget(telemetry_group)

        recovery_group = QGroupBox("Crash recovery tools")
        recovery_layout = QVBoxLayout(recovery_group)
        recovery_layout.setContentsMargins(12, 12, 12, 12)

        safe_mode_hint = QLabel(
            "Safe Mode disables background diagnostics and cache inspection so you can troubleshoot "
            "launch issues. The app must be restarted for this to take effect."
        )
        safe_mode_hint.setWordWrap(True)
        safe_mode_hint.setStyleSheet("color: #5f6673;")
        recovery_layout.addWidget(safe_mode_hint)

        self._safe_mode_status = QLabel()
        self._safe_mode_status.setWordWrap(True)
        recovery_layout.addWidget(self._safe_mode_status)

        safe_mode_buttons = QHBoxLayout()
        self._request_safe_mode_button = QPushButton("Request Safe Mode on next launch")
        self._request_safe_mode_button.clicked.connect(self._request_safe_mode)
        safe_mode_buttons.addWidget(self._request_safe_mode_button)
        self._cancel_safe_mode_button = QPushButton("Cancel Safe Mode request")
        self._cancel_safe_mode_button.clicked.connect(self._cancel_safe_mode_request)
        safe_mode_buttons.addWidget(self._cancel_safe_mode_button)
        safe_mode_buttons.addStretch()
        recovery_layout.addLayout(safe_mode_buttons)

        purge_hint = QLabel(
            "Schedule a Graph cache purge to run before services initialise. This helps recover from "
            "corrupted local caches without manually deleting files."
        )
        purge_hint.setWordWrap(True)
        purge_hint.setStyleSheet("color: #5f6673;")
        recovery_layout.addWidget(purge_hint)

        self._purge_status = QLabel()
        self._purge_status.setWordWrap(True)
        recovery_layout.addWidget(self._purge_status)

        purge_buttons = QHBoxLayout()
        self._request_purge_button = QPushButton("Purge caches on next launch")
        self._request_purge_button.clicked.connect(self._request_cache_purge)
        purge_buttons.addWidget(self._request_purge_button)
        self._cancel_purge_button = QPushButton("Cancel purge request")
        self._cancel_purge_button.clicked.connect(self._cancel_cache_purge_request)
        purge_buttons.addWidget(self._cancel_purge_button)
        purge_buttons.addStretch()
        recovery_layout.addLayout(purge_buttons)

        layout.addWidget(recovery_group)

        layout.addStretch()

    def _refresh_logs(self) -> None:
        self._log_list.clear()
        files = self._diagnostics.log_files()
        if not files:
            QListWidgetItem("No log files generated yet", self._log_list)
            return
        for file in files:
            size = file.stat().st_size if file.exists() else 0
            QListWidgetItem(f"{file.name} — {self._format_bytes(size)}", self._log_list)

    def _open_log_folder(self) -> None:
        files = self._diagnostics.log_files()
        if not files:
            QMessageBox.information(self, "Logs", "No logs available yet.")
            return
        directory = files[0].parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    def _export_logs(self) -> None:
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Export logs",
            str(Path.home() / "intune-manager-logs.zip"),
            "Zip archives (*.zip)",
        )
        if not target:
            return
        try:
            result = self._diagnostics.export_logs(Path(target))
        except FileNotFoundError:
            QMessageBox.warning(self, "Export failed", "No log files to export yet.")
            return
        QMessageBox.information(
            self,
            "Logs exported",
            f"Exported logs to {result}.",
        )

    def _refresh_keyring(self) -> None:
        statuses = self._diagnostics.secret_presence()
        lines = []
        for label, present in statuses.items():
            state = "Stored" if present else "Not stored"
            lines.append(f"{label}: {state}")
        self._keyring_label.setText("\n".join(lines))

    def _handle_telemetry_toggled(self, checked: bool) -> None:
        self._diagnostics.set_telemetry_opt_in(checked)
        self.telemetryChanged.emit(checked)

    def _apply_telemetry_state(self) -> None:
        enabled = self._diagnostics.telemetry_opt_in()
        self._telemetry_toggle.blockSignals(True)
        self._telemetry_toggle.setChecked(enabled)
        self._telemetry_toggle.blockSignals(False)

    def _refresh_recovery_status(self) -> None:
        safe_mode_info = pending_safe_mode_request()
        if safe_mode_info:
            self._safe_mode_status.setText(
                self._format_request_status(
                    safe_mode_info,
                    prefix="Safe Mode request pending",
                )
            )
            self._cancel_safe_mode_button.setEnabled(True)
        else:
            self._safe_mode_status.setText("Safe Mode not scheduled.")
            self._cancel_safe_mode_button.setEnabled(False)

        purge_info = pending_cache_purge_request()
        if purge_info:
            self._purge_status.setText(
                self._format_request_status(
                    purge_info,
                    prefix="Cache purge scheduled",
                )
            )
            self._cancel_purge_button.setEnabled(True)
        else:
            self._purge_status.setText("No cache purge queued.")
            self._cancel_purge_button.setEnabled(False)

    def _format_request_status(self, info: dict[str, object], *, prefix: str) -> str:
        reason = info.get("reason") or "Manual request"
        timestamp = info.get("requested_at")
        if isinstance(timestamp, str):
            try:
                readable = (
                    datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    .astimezone()
                    .strftime("%Y-%m-%d %H:%M:%S %Z")
                )
            except ValueError:
                readable = timestamp
        else:
            readable = "unknown time"
        return f"{prefix} — {reason} at {readable}."

    def _request_safe_mode(self) -> None:
        schedule_safe_mode_request("Diagnostics tab request")
        QMessageBox.information(
            self,
            "Safe Mode scheduled",
            (
                "Safe Mode will be enabled the next time you launch Intune Manager. "
                "Restart the application to continue in Safe Mode."
            ),
        )
        self._refresh_recovery_status()

    def _cancel_safe_mode_request(self) -> None:
        cancel_safe_mode_request()
        QMessageBox.information(
            self,
            "Safe Mode request cleared",
            "Safe Mode will no longer be enabled automatically on next launch.",
        )
        self._refresh_recovery_status()

    def _request_cache_purge(self) -> None:
        reply = QMessageBox.question(
            self,
            "Schedule cache purge",
            (
                "Purge cached Graph data at the beginning of the next launch?\n\n"
                "This runs before services start and may help recover from corrupted caches."
            ),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        schedule_cache_purge_request("Diagnostics tab request")
        QMessageBox.information(
            self,
            "Cache purge scheduled",
            "Cached Graph data will be cleared automatically on the next launch.",
        )
        self._refresh_recovery_status()

    def _cancel_cache_purge_request(self) -> None:
        cancel_cache_purge_request()
        QMessageBox.information(
            self,
            "Cache purge cancelled",
            "Startup cache purge has been cancelled.",
        )
        self._refresh_recovery_status()

    def _format_bytes(self, value: int) -> str:
        if value < 1024:
            return f"{value} B"
        units = ["KiB", "MiB", "GiB", "TiB"]
        size = float(value)
        for unit in units:
            size /= 1024.0
            if size < 1024.0:
                return f"{size:.2f} {unit}"
        return f"{size:.2f} PiB"


class AboutWidget(QWidget):
    """Display application metadata and accessibility notes."""

    def __init__(
        self,
        *,
        diagnostics: DiagnosticsService | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._diagnostics = diagnostics
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        accessibility_group = QGroupBox("Accessibility")
        accessibility_layout = QVBoxLayout(accessibility_group)
        accessibility_layout.setContentsMargins(12, 12, 12, 12)

        accessibility_label = QLabel(
            "Intune Manager uses a high-contrast light theme with prominent focus indicators "
            "and keyboard navigation support across modules.",
        )
        accessibility_label.setWordWrap(True)
        accessibility_layout.addWidget(accessibility_label)
        layout.addWidget(accessibility_group)

        about_group = QGroupBox("About Intune Manager")
        about_layout = QVBoxLayout(about_group)
        about_layout.setContentsMargins(12, 12, 12, 12)

        self._about_browser = QTextBrowser()
        self._about_browser.setOpenExternalLinks(True)
        self._about_browser.setReadOnly(True)
        self._about_browser.setFrameStyle(QTextBrowser.NoFrame)
        self._about_browser.setHtml(self._about_markup())
        about_layout.addWidget(self._about_browser)
        layout.addWidget(about_group)

        layout.addStretch()

    def refresh(self, *_: object) -> None:
        self._about_browser.setHtml(self._about_markup())

    def _about_markup(self) -> str:
        version = self._resolve_version()
        telemetry_hint = (
            "Enabled"
            if self._diagnostics and self._diagnostics.telemetry_opt_in()
            else "Disabled"
        )
        return (
            "<h3>Intune Manager</h3>"
            f"<p><b>Version:</b> {version}</p>"
            "<p><b>Theme:</b> Light (high-contrast)</p>"
            f"<p><b>Telemetry:</b> {telemetry_hint}</p>"
            "<p>Cross-platform Microsoft Intune administration console built with PySide6.\n"
            "View the project on <a href='https://github.com'>GitHub</a> and read the "
            "<a href='https://github.com/microsoftgraph/msgraph-sdk-python'>Graph SDK docs</a>.</p>"
            "<p>Licensed under the MIT License.</p>"
        )

    def _resolve_version(self) -> str:
        try:
            from importlib.metadata import PackageNotFoundError, version

            return version("intune-manager-python")
        except PackageNotFoundError:  # pragma: no cover - editable install fallback
            return "dev"
        except Exception:  # pragma: no cover - other metadata lookup issues
            return "dev"


__all__ = ["SettingsPage", "CacheManagementWidget", "DiagnosticsWidget", "AboutWidget"]
