from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterable, List

from PySide6.QtCore import QItemSelection, QModelIndex, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QSpinBox,
    QTextEdit,
)

from intune_manager.data import AuditEvent
from intune_manager.services import ServiceErrorEvent, ServiceRegistry
from intune_manager.ui.components import (
    InlineStatusMessage,
    PageScaffold,
    ToastLevel,
    UIContext,
    make_toolbar_button,
)
from intune_manager.ui.reports.controller import AuditLogController
from intune_manager.ui.reports.models import (
    AuditEventFilterProxyModel,
    AuditEventTableModel,
)
from intune_manager.utils.errors import ErrorSeverity, describe_exception


def _toast_level_for(severity: ErrorSeverity) -> ToastLevel:
    try:
        return ToastLevel(severity.value)
    except ValueError:  # pragma: no cover - defensive mapping fallback
        return ToastLevel.ERROR


def _format_filesize(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    index = 0
    while value >= 1024 and index < len(units) - 1:
        value /= 1024
        index += 1
    if index == 0:
        return f"{int(value)} {units[index]}"
    return f"{value:.1f} {units[index]}"


def _format_mtime(timestamp: float) -> str:
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


class AuditEventDetailPane(QWidget):
    """Display details for the selected audit event."""

    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._stack = QVBoxLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.setSpacing(8)

        self._title_label = QLabel("Select an audit event to inspect activity details.")
        self._title_label.setWordWrap(True)
        self._title_label.setStyleSheet("color: palette(mid);")
        self._stack.addWidget(self._title_label)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setObjectName("AuditEventDetailText")
        self._text.setMinimumHeight(280)
        self._stack.addWidget(self._text, stretch=1)

        self.display_event(None)

    def display_event(self, event: AuditEvent | None) -> None:
        if event is None:
            self._title_label.setText(
                "Select an audit event to inspect activity details."
            )
            self._text.setPlainText("")
            return

        timestamp = (
            event.activity_date_time.strftime("%Y-%m-%d %H:%M:%S")
            if event.activity_date_time
            else "Unknown"
        )
        summary_lines = [
            f"Activity: {event.activity or 'Unknown'}",
            f"Component: {event.component_name or 'Unknown'}",
            f"Result: {event.activity_result or 'Unknown'}",
            f"Category: {event.category or 'Unspecified'}",
            f"Timestamp: {timestamp}",
            f"Correlation ID: {event.correlation_id or 'N/A'}",
        ]

        actor = event.actor
        if actor is not None:
            actor_lines = ["", "Actor:"]
            if actor.user_principal_name:
                actor_lines.append(f"  UPN: {actor.user_principal_name}")
            if actor.service_principal_name:
                actor_lines.append(
                    f"  Service Principal: {actor.service_principal_name}"
                )
            if actor.application_display_name:
                actor_lines.append(f"  App: {actor.application_display_name}")
            if actor.ip_address:
                actor_lines.append(f"  IP: {actor.ip_address}")
            if actor.user_permissions:
                actor_lines.append(
                    f"  Permissions: {', '.join(actor.user_permissions)}"
                )
            summary_lines.extend(actor_lines)

        resources = event.resources or []
        if resources:
            summary_lines.append("")
            summary_lines.append("Resources:")
            for resource in resources:
                name = (
                    resource.display_name
                    or resource.resource_id
                    or resource.type
                    or "Unknown"
                )
                summary_lines.append(f"  - {name}")

        self._title_label.setText(
            event.display_name or event.activity or "Audit Event Details"
        )
        self._text.setPlainText("\n".join(summary_lines))


class ReportsWidget(PageScaffold):
    """Audit logs and diagnostics workspace."""

    _DATE_PRESETS: dict[str, timedelta] = {
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
    }

    def __init__(
        self,
        services: ServiceRegistry,
        *,
        context: UIContext,
        parent: QWidget | None = None,
    ) -> None:
        self._services = services
        self._context = context
        self._controller = AuditLogController(services)
        self._model = AuditEventTableModel()
        self._proxy = AuditEventFilterProxyModel()
        self._proxy.setSourceModel(self._model)

        self._selected_event: AuditEvent | None = None

        self._refresh_button = make_toolbar_button(
            "Refresh", tooltip="Refresh audit events from cache/Graph."
        )
        self._force_refresh_button = make_toolbar_button(
            "Force refresh",
            tooltip="Bypass cache checks and query Microsoft Graph immediately.",
        )
        self._export_button = make_toolbar_button(
            "Export JSON", tooltip="Export cached audit events to a JSON file."
        )
        self._copy_button = make_toolbar_button(
            "Copy JSON", tooltip="Copy selected audit event as JSON."
        )
        self._copy_button.setEnabled(False)

        actions: List[QToolButton] = [
            self._refresh_button,
            self._force_refresh_button,
            self._export_button,
            self._copy_button,
        ]

        super().__init__(
            "Reports",
            subtitle="Review Intune audit events and collect local diagnostic logs for troubleshooting.",
            actions=actions,
            parent=parent,
        )

        self._build_filters()
        self._build_tabs()

        self._refresh_button.clicked.connect(lambda: self._start_refresh(force=False))
        self._force_refresh_button.clicked.connect(
            lambda: self._start_refresh(force=True)
        )
        self._export_button.clicked.connect(self._handle_export_clicked)
        self._copy_button.clicked.connect(self._handle_copy_clicked)

        self._controller.register_callbacks(
            refreshed=self._handle_events_refreshed,
            error=self._handle_service_error,
        )

        self._load_cached_events()
        self._load_diagnostic_logs()
        self._update_action_states()

        if self._services.audit is None:
            self._handle_service_unavailable()

        self.destroyed.connect(lambda *_: self._controller.dispose())

    # ----------------------------------------------------------------- Build UI

    def _build_filters(self) -> None:
        self._filters_widget = QWidget()
        layout = QHBoxLayout(self._filters_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search activity, actor, resource…")
        self._search_input.textChanged.connect(self._handle_search_changed)
        layout.addWidget(self._search_input, stretch=3)

        self._date_combo = QComboBox()
        self._date_combo.addItem("Cached (no filter)", userData=None)
        self._date_combo.addItem("Last 24 hours", userData="24h")
        self._date_combo.addItem("Last 7 days", userData="7d")
        self._date_combo.addItem("Last 30 days", userData="30d")
        layout.addWidget(self._date_combo)

        self._top_spin = QSpinBox()
        self._top_spin.setMinimum(50)
        self._top_spin.setMaximum(1000)
        self._top_spin.setSingleStep(50)
        self._top_spin.setValue(200)
        self._top_spin.setSuffix(" events")
        self._top_spin.setToolTip("Maximum events to request per refresh.")
        layout.addWidget(self._top_spin)

        self._result_combo = QComboBox()
        self._result_combo.addItem("All results", userData=None)
        self._result_combo.addItem("Success", userData="Success")
        self._result_combo.addItem("Failure", userData="Failure")
        self._result_combo.addItem("Other", userData="Other")
        self._result_combo.currentIndexChanged.connect(self._handle_result_changed)
        layout.addWidget(self._result_combo)

        self._category_combo = QComboBox()
        self._category_combo.addItem("All categories", userData=None)
        self._category_combo.currentIndexChanged.connect(self._handle_category_changed)
        layout.addWidget(self._category_combo)

        self._summary_label = QLabel("No events loaded.")
        self._summary_label.setStyleSheet("color: palette(mid);")
        layout.addWidget(self._summary_label, stretch=2)

        self.body_layout.addWidget(self._filters_widget)

    def _build_tabs(self) -> None:
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.addTab(self._build_audit_tab(), "Audit events")
        self._tabs.addTab(self._build_diagnostics_tab(), "Diagnostic logs")
        self.body_layout.addWidget(self._tabs, stretch=1)

    def _build_audit_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._audit_message = InlineStatusMessage(parent=container)
        layout.addWidget(self._audit_message)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table_layout.addWidget(self._table, stretch=1)

        splitter.addWidget(table_container)

        self._detail_pane = AuditEventDetailPane(parent=splitter)
        splitter.addWidget(self._detail_pane)
        splitter.setSizes([640, 340])

        layout.addWidget(splitter, stretch=1)

        selection_model = self._table.selectionModel()
        if selection_model is not None:
            selection_model.selectionChanged.connect(self._handle_selection_changed)

        self._proxy.modelReset.connect(self._update_summary)
        self._proxy.rowsInserted.connect(lambda *_: self._update_summary())
        self._proxy.rowsRemoved.connect(lambda *_: self._update_summary())
        self._model.modelReset.connect(self._handle_model_reset)

        return container

    def _build_diagnostics_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._diag_message = InlineStatusMessage(parent=container)
        layout.addWidget(self._diag_message)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)

        self._diag_refresh_button = QToolButton()
        self._diag_refresh_button.setText("Refresh list")
        self._diag_refresh_button.clicked.connect(self._load_diagnostic_logs)
        controls.addWidget(self._diag_refresh_button)

        self._diag_export_button = QToolButton()
        self._diag_export_button.setText("Export bundle…")
        self._diag_export_button.clicked.connect(self._handle_export_logs_clicked)
        controls.addWidget(self._diag_export_button)

        self._diag_save_button = QToolButton()
        self._diag_save_button.setText("Save selected…")
        self._diag_save_button.clicked.connect(self._handle_save_selected_log)
        self._diag_save_button.setEnabled(False)
        controls.addWidget(self._diag_save_button)

        self._diag_open_button = QToolButton()
        self._diag_open_button.setText("Open folder")
        self._diag_open_button.clicked.connect(self._handle_open_log_folder)
        controls.addWidget(self._diag_open_button)

        controls.addStretch(1)
        layout.addLayout(controls)

        self._diag_list = QListWidget()
        self._diag_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._diag_list.itemSelectionChanged.connect(
            self._handle_diag_selection_changed
        )
        layout.addWidget(self._diag_list, stretch=1)

        return container

    # ----------------------------------------------------------------- Data flow

    def _load_cached_events(self) -> None:
        events = self._controller.list_cached()
        self._set_events(events, from_cache=True)

    def _set_events(self, events: Iterable[AuditEvent], *, from_cache: bool) -> None:
        events_list = list(events)
        self._audit_message.clear()
        self._model.set_events(events_list)
        self._populate_category_filter(events_list)
        self._apply_filters()
        self._auto_select_first_row()
        self._update_summary()
        self._update_action_states()
        if not events_list and from_cache:
            self._detail_pane.display_event(None)

    def _populate_category_filter(self, events: Iterable[AuditEvent]) -> None:
        current = self._category_combo.currentData()
        categories = sorted(
            {
                (event.category or "").strip()
                for event in events
                if (event.category or "").strip()
            }
        )
        self._category_combo.blockSignals(True)
        self._category_combo.clear()
        self._category_combo.addItem("All categories", userData=None)
        for category in categories:
            self._category_combo.addItem(category, userData=category)
        self._category_combo.blockSignals(False)
        if current:
            index = self._category_combo.findData(current)
            if index >= 0:
                self._category_combo.setCurrentIndex(index)

    def _apply_filters(self) -> None:
        self._proxy.set_search_text(self._search_input.text())
        self._proxy.set_category_filter(self._category_combo.currentData())
        self._proxy.set_result_filter(self._result_combo.currentData())

    def _auto_select_first_row(self) -> None:
        if self._proxy.rowCount() == 0:
            self._selected_event = None
            self._copy_button.setEnabled(False)
            self._detail_pane.display_event(None)
            return
        self._table.selectRow(0)

    # ----------------------------------------------------------------- Actions

    def _start_refresh(self, *, force: bool) -> None:
        if self._services.audit is None:
            self._handle_service_unavailable()
            return
        filter_expression = self._build_filter_expression()
        top = self._top_spin.value()
        self._audit_message.clear()
        self._context.set_busy("Refreshing audit events…")
        self._refresh_button.setEnabled(False)
        self._force_refresh_button.setEnabled(False)
        self._context.run_async(
            self._refresh_async(
                force=force, filter_expression=filter_expression, top=top
            )
        )

    async def _refresh_async(
        self, *, force: bool, filter_expression: str | None, top: int
    ) -> None:
        try:
            await self._controller.refresh(
                force=force,
                filter_expression=filter_expression,
                top=top,
            )
        except Exception as exc:  # noqa: BLE001
            descriptor = describe_exception(exc)
            detail_lines = [descriptor.detail]
            if descriptor.transient:
                detail_lines.append("This issue may resolve after retrying.")
            if descriptor.suggestion:
                detail_lines.append(f"Suggested action: {descriptor.suggestion}")
            detail_text = "\n\n".join(detail_lines)
            level = _toast_level_for(descriptor.severity)
            self._audit_message.display(
                descriptor.headline, level=level, detail=detail_text
            )
            self._context.show_notification(descriptor.headline, level=level)
            self._context.clear_busy()
            self._refresh_button.setEnabled(True)
            self._force_refresh_button.setEnabled(True)

    def _handle_export_clicked(self) -> None:
        if self._services.export is None:
            self._context.show_notification(
                "Export service is not configured.",
                level=ToastLevel.WARNING,
            )
            return
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Export audit events",
            "audit-events.json",
            "JSON Files (*.json)",
        )
        if not path_str:
            return
        path = Path(path_str)
        try:
            exported = self._controller.export_all(path)
        except Exception as exc:  # noqa: BLE001
            descriptor = describe_exception(exc)
            level = _toast_level_for(descriptor.severity)
            detail = descriptor.detail
            if descriptor.suggestion:
                detail = f"{detail}\n\nSuggested action: {descriptor.suggestion}"
            self._audit_message.display(descriptor.headline, level=level, detail=detail)
            self._context.show_notification(descriptor.headline, level=level)
            return
        self._context.show_notification(
            f"Exported audit events to {exported.name}", level=ToastLevel.SUCCESS
        )

    def _handle_copy_clicked(self) -> None:
        if self._selected_event is None:
            return
        payload = self._selected_event.to_graph()
        text = json.dumps(payload, indent=2)
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(text)
        self._context.show_notification(
            "Audit event copied to clipboard.", level=ToastLevel.SUCCESS
        )

    # ------------------------------------------------------------- Diagnostics

    def _load_diagnostic_logs(self) -> None:
        service = self._services.diagnostics
        if service is None:
            self._diag_message.display(
                "Diagnostics service unavailable. Configure local logging before exporting bundles.",
                level=ToastLevel.WARNING,
            )
            self._diag_list.clear()
            self._diag_refresh_button.setEnabled(False)
            self._diag_export_button.setEnabled(False)
            self._diag_save_button.setEnabled(False)
            self._diag_open_button.setEnabled(False)
            return

        self._diag_message.clear()
        self._diag_refresh_button.setEnabled(True)
        self._diag_export_button.setEnabled(True)
        self._diag_open_button.setEnabled(True)

        self._diag_list.clear()
        for path in service.log_files():
            stat = path.stat()
            label = f"{path.name} — {_format_filesize(stat.st_size)} · {_format_mtime(stat.st_mtime)}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self._diag_list.addItem(item)

        has_items = self._diag_list.count() > 0
        self._diag_save_button.setEnabled(
            has_items and bool(self._diag_list.selectedItems())
        )

    def _handle_export_logs_clicked(self) -> None:
        service = self._services.diagnostics
        if service is None:
            return
        suggested_name = (
            f"intune-manager-logs-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.zip"
        )
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Export diagnostic logs",
            suggested_name,
            "ZIP Archives (*.zip)",
        )
        if not path_str:
            return
        target = Path(path_str)
        try:
            path = service.export_logs(target)
        except Exception as exc:  # noqa: BLE001
            descriptor = describe_exception(exc)
            level = _toast_level_for(descriptor.severity)
            detail = descriptor.detail
            if descriptor.suggestion:
                detail = f"{detail}\n\nSuggested action: {descriptor.suggestion}"
            self._diag_message.display(descriptor.headline, level=level, detail=detail)
            self._context.show_notification(descriptor.headline, level=level)
            return
        self._context.show_notification(
            f"Exported diagnostic logs to {path.name}", level=ToastLevel.SUCCESS
        )

    def _handle_save_selected_log(self) -> None:
        service = self._services.diagnostics
        if service is None:
            return
        selected = self._diag_list.selectedItems()
        if not selected:
            self._context.show_notification(
                "Select at least one log file to save.", level=ToastLevel.WARNING
            )
            return
        directory = QFileDialog.getExistingDirectory(self, "Select destination folder")
        if not directory:
            return
        dest_dir = Path(directory)
        errors: list[str] = []
        for item in selected:
            path = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(path, Path):
                continue
            try:
                shutil.copy(path, dest_dir / path.name)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{path.name}: {exc}")
        if errors:
            QMessageBox.warning(
                self,
                "Save logs",
                "\n".join(errors),
            )
        else:
            self._context.show_notification(
                f"Saved {len(selected)} log file(s) to {dest_dir.name}",
                level=ToastLevel.SUCCESS,
            )

    def _handle_open_log_folder(self) -> None:
        service = self._services.diagnostics
        if service is None:
            return
        selected = self._diag_list.selectedItems()
        if selected:
            path = selected[0].data(Qt.ItemDataRole.UserRole)
        else:
            files = service.log_files()
            path = files[0] if files else None
        if not isinstance(path, Path):
            self._context.show_notification(
                "No log files available to open.", level=ToastLevel.WARNING
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    def _handle_diag_selection_changed(self) -> None:
        self._diag_save_button.setEnabled(bool(self._diag_list.selectedItems()))

    # ----------------------------------------------------------------- Callbacks

    def _handle_events_refreshed(
        self, events: Iterable[AuditEvent], from_cache: bool
    ) -> None:
        self._context.clear_busy()
        self._refresh_button.setEnabled(True)
        self._force_refresh_button.setEnabled(True)
        self._set_events(events, from_cache=from_cache)
        self._update_action_states()
        if not from_cache:
            count = self._model.rowCount()
            self._context.show_notification(
                f"Loaded {count:,} audit events from Microsoft Graph.",
                level=ToastLevel.SUCCESS,
            )

    def _handle_service_error(self, event: ServiceErrorEvent) -> None:
        self._context.clear_busy()
        self._refresh_button.setEnabled(True)
        self._force_refresh_button.setEnabled(True)
        descriptor = describe_exception(event.error)
        detail_lines = [descriptor.detail]
        if descriptor.transient:
            detail_lines.append("This issue may resolve after retrying.")
        if descriptor.suggestion:
            detail_lines.append(f"Suggested action: {descriptor.suggestion}")
        detail_text = "\n\n".join(detail_lines)
        level = _toast_level_for(descriptor.severity)
        self._audit_message.display(
            descriptor.headline, level=level, detail=detail_text
        )
        self._context.show_notification(descriptor.headline, level=level)

    def _handle_selection_changed(
        self, selected: QItemSelection, deselected: QItemSelection
    ) -> None:  # noqa: ARG002
        indexes = selected.indexes()
        if not indexes:
            self._selected_event = None
            self._copy_button.setEnabled(False)
            self._detail_pane.display_event(None)
            self._update_summary()
            return
        index: QModelIndex = indexes[0]
        event = self._proxy.data(index, Qt.ItemDataRole.UserRole)
        if isinstance(event, AuditEvent):
            self._selected_event = event
            self._copy_button.setEnabled(True)
            self._detail_pane.display_event(event)
        else:
            self._selected_event = None
            self._copy_button.setEnabled(False)
            self._detail_pane.display_event(None)
        self._update_summary()
        self._update_action_states()

    def _handle_model_reset(self) -> None:
        self._auto_select_first_row()
        self._update_summary()

    def _handle_search_changed(self, text: str) -> None:
        self._proxy.set_search_text(text)
        self._update_summary()

    def _handle_category_changed(self, _: int) -> None:
        self._proxy.set_category_filter(self._category_combo.currentData())
        self._update_summary()

    def _handle_result_changed(self, _: int) -> None:
        self._proxy.set_result_filter(self._result_combo.currentData())
        self._update_summary()

    # ----------------------------------------------------------------- Helpers

    def _build_filter_expression(self) -> str | None:
        preset = self._date_combo.currentData()
        if preset is None:
            return None
        delta = self._DATE_PRESETS.get(preset)
        if delta is None:
            return None
        threshold = (datetime.now(UTC) - delta).replace(microsecond=0)
        timestamp = threshold.isoformat(timespec="seconds").replace("+00:00", "Z")
        return f"activityDateTime ge {timestamp}"

    def _update_summary(self) -> None:
        visible = self._proxy.rowCount()
        total = self._model.rowCount()
        parts = [f"{visible:,} events shown"]
        if visible != total:
            parts.append(f"{total:,} cached")
        if self._controller.is_cache_stale():
            parts.append("Cache stale — refresh recommended")
        if self._selected_event is not None:
            parts.append("1 selected")
        self._summary_label.setText(" · ".join(parts))

    def _update_action_states(self) -> None:
        service_available = self._services.audit is not None
        self._refresh_button.setEnabled(service_available)
        self._force_refresh_button.setEnabled(service_available)
        self._export_button.setEnabled(
            service_available
            and self._model.rowCount() > 0
            and self._services.export is not None
        )
        self._copy_button.setEnabled(self._selected_event is not None)

    def _handle_service_unavailable(self) -> None:
        self._audit_message.display(
            "Audit service unavailable. Configure Microsoft Graph credentials before viewing audit logs.",
            level=ToastLevel.WARNING,
        )
        self._table.setEnabled(False)
        self._detail_pane.display_event(None)
        self._refresh_button.setEnabled(False)
        self._force_refresh_button.setEnabled(False)
        self._export_button.setEnabled(False)
        self._copy_button.setEnabled(False)
        self._update_action_states()


__all__ = ["ReportsWidget"]
