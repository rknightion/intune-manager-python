from __future__ import annotations

from dataclasses import dataclass
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

from intune_manager.services import DiagnosticsService
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
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._diagnostics = diagnostics
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
            self._cache_tab = CacheManagementWidget(self._diagnostics, parent=self)
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

    def __init__(self, diagnostics: DiagnosticsService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._diagnostics = diagnostics
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

        inspect_button = QPushButton("Inspect & repair cache")
        inspect_button.clicked.connect(self._run_inspection)
        status_layout.addWidget(inspect_button)

        layout.addWidget(status_group)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["Resource", "Scope", "Recorded", "Actual", "Repaired", "Issues"],
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
        purge_button = QPushButton("Purge attachments")
        purge_button.clicked.connect(self._purge_attachments)
        attachment_layout.addWidget(purge_button)
        layout.addWidget(attachment_group)

        action_row = QHBoxLayout()
        action_row.addStretch()
        clear_button = QPushButton("Clear all cached data")
        clear_button.clicked.connect(self._clear_all)
        action_row.addWidget(clear_button)
        layout.addLayout(action_row)

        layout.addStretch()

    def _run_inspection(self) -> None:
        reply = QMessageBox.question(
            self,
            "Inspect cache",
            (
                "Run cache validation now? This may purge invalid records automatically."
            ),
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
            style = SEVERITY_STYLES.get(severity_key, CacheSeverityStyle("Unknown", "#5f6673"))
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
            self._table.setItem(row, 1, QTableWidgetItem(entry.scope))
            recorded = "–" if entry.recorded_count is None else str(entry.recorded_count)
            self._table.setItem(row, 2, QTableWidgetItem(recorded))
            self._table.setItem(row, 3, QTableWidgetItem(str(entry.actual_count)))
            repaired_text = "Yes" if entry.repaired else "No"
            self._table.setItem(row, 4, QTableWidgetItem(repaired_text))
            issue_lines = [f"[{issue.severity.value.upper()}] {issue.message}" for issue in entry.issues]
            issue_text = "\n".join(issue_lines)
            self._table.setItem(row, 5, QTableWidgetItem(issue_text))
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


class DiagnosticsWidget(QWidget):
    """Expose log export, keyring status, and telemetry preferences."""

    telemetryChanged = Signal(bool)

    def __init__(self, diagnostics: DiagnosticsService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._diagnostics = diagnostics
        self._build_ui()
        self._refresh_logs()
        self._refresh_keyring()
        self._apply_telemetry_state()

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
        self._telemetry_toggle = QCheckBox("Share anonymised diagnostics to improve Intune Manager")
        self._telemetry_toggle.toggled.connect(self._handle_telemetry_toggled)
        telemetry_layout.addWidget(self._telemetry_toggle)
        hint = QLabel(
            "Telemetry never includes tenant IDs or personal information. Toggle to help improve reliability.",
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #5f6673;")
        telemetry_layout.addWidget(hint)
        layout.addWidget(telemetry_group)

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
        telemetry_hint = "Enabled" if self._diagnostics and self._diagnostics.telemetry_opt_in() else "Disabled"
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
