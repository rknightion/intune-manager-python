from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Iterable, List

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFormLayout,
    QGroupBox,
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
    QComboBox,
)

from intune_manager.data import (
    AttachmentMetadata,
    AssignmentFilter,
    DirectoryGroup,
    MobileApp,
    MobileAppAssignment,
)
from intune_manager.services import ServiceErrorEvent, ServiceRegistry
from intune_manager.services.applications import InstallSummaryEvent
from intune_manager.ui.components import (
    CommandAction,
    PageScaffold,
    ToastLevel,
    UIContext,
    make_toolbar_button,
)

from .assignment_editor import AssignmentEditorDialog
from .controller import ApplicationController
from .models import ApplicationFilterProxyModel, ApplicationTableModel


def _format_value(value: object | None) -> str:
    if value is None:
        return "—"
    return str(value)


class ApplicationDetailPane(QWidget):
    """Right-hand pane presenting selected application details."""

    _INTENT_BADGES = {
        "required": ("Required", "#2563eb"),
        "available": ("Available", "#059669"),
        "uninstall": ("Uninstall", "#dc2626"),
        "availableWithoutEnrollment": ("Available (BYOD)", "#7c3aed"),
    }

    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)

        self._icon_label = QLabel()
        self._icon_label.setFixedSize(96, 96)
        self._icon_label.setScaledContents(True)
        self._icon_label.setStyleSheet("border: 1px solid palette(midlight); border-radius: 12px;")
        header_layout.addWidget(self._icon_label)

        title_container = QWidget()
        title_layout = QVBoxLayout(title_container)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(4)

        self._title_label = QLabel("Select an application")
        title_font = self._title_label.font()
        title_font.setPointSizeF(title_font.pointSizeF() + 2)
        title_font.setWeight(QFont.Weight.DemiBold)
        self._title_label.setFont(title_font)

        self._subtitle_label = QLabel("")
        self._subtitle_label.setWordWrap(True)
        self._subtitle_label.setStyleSheet("color: palette(mid);")

        title_layout.addWidget(self._title_label)
        title_layout.addWidget(self._subtitle_label)

        self._badge_container = QWidget()
        self._badge_layout = QHBoxLayout(self._badge_container)
        self._badge_layout.setContentsMargins(0, 0, 0, 0)
        self._badge_layout.setSpacing(6)
        title_layout.addWidget(self._badge_container)

        header_layout.addWidget(title_container, stretch=1)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        self._tab_widget = QTabWidget()
        self._tab_widget.setDocumentMode(True)
        layout.addWidget(self._tab_widget, stretch=1)

        # Overview tab
        self._overview_tab = QWidget()
        overview_layout = QVBoxLayout(self._overview_tab)
        overview_layout.setContentsMargins(0, 0, 0, 0)
        overview_layout.setSpacing(12)

        self._description_label = QLabel()
        self._description_label.setWordWrap(True)
        self._description_label.setStyleSheet("color: palette(mid);")
        overview_layout.addWidget(self._description_label)

        form_group = QGroupBox("Metadata")
        form_layout = QFormLayout(form_group)
        form_layout.setContentsMargins(12, 8, 12, 8)
        form_layout.setSpacing(6)
        self._fields: dict[str, QLabel] = {}
        for key, label in [
            ("platform", "Platform"),
            ("publisher", "Publisher"),
            ("owner", "Owner"),
            ("developer", "Developer"),
            ("created", "Created"),
            ("modified", "Last modified"),
            ("categories", "Categories"),
        ]:
            value_label = QLabel("—")
            value_label.setWordWrap(True)
            self._fields[key] = value_label
            form_layout.addRow(f"{label}:", value_label)
        overview_layout.addWidget(form_group)
        overview_layout.addStretch()

        # Assignments tab
        self._assignments_tab = QWidget()
        assignments_layout = QVBoxLayout(self._assignments_tab)
        assignments_layout.setContentsMargins(0, 0, 0, 0)
        assignments_layout.setSpacing(6)
        assignments_hint = QLabel(
            "Assignments reflect the cached state. Use the editor to add/remove groups and adjust intents.",
        )
        assignments_hint.setWordWrap(True)
        assignments_hint.setStyleSheet("color: palette(mid);")
        assignments_layout.addWidget(assignments_hint)
        self._assignments_list = QListWidget()
        self._assignments_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        assignments_layout.addWidget(self._assignments_list, stretch=1)

        # Install status tab
        self._install_tab = QWidget()
        install_layout = QVBoxLayout(self._install_tab)
        install_layout.setContentsMargins(0, 0, 0, 0)
        install_layout.setSpacing(6)
        install_hint = QLabel("Fetch install summaries to review deployment cohorts and drill into raw payloads.")
        install_hint.setWordWrap(True)
        install_hint.setStyleSheet("color: palette(mid);")
        install_layout.addWidget(install_hint)
        self._install_summary_list = QListWidget()
        self._install_summary_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._install_summary_list.itemActivated.connect(self._handle_install_summary_activated)
        install_layout.addWidget(self._install_summary_list, stretch=1)

        self._tab_widget.addTab(self._overview_tab, "Overview")
        self._tab_widget.addTab(self._assignments_tab, "Assignments")
        self._tab_widget.addTab(self._install_tab, "Install status")

        self._current_install_summary: dict[str, object] | None = None

    def display_app(self, app: MobileApp | None, icon: QIcon | None) -> None:
        if app is None:
            self._title_label.setText("Select an application")
            self._subtitle_label.setText("")
            self._description_label.setText("")
            self._clear_badges()
            self._set_icon(icon)
            for label in self._fields.values():
                label.setText("—")
            self._assignments_list.clear()
            self.update_install_summary(None)
            return

        self._title_label.setText(app.display_name)
        subtitle_parts = [app.owner or "", app.publisher or ""]
        self._subtitle_label.setText(" · ".join(part for part in subtitle_parts if part))
        self._description_label.setText(app.description or "")
        self._update_badges(app)

        platform = app.platform_type.value if app.platform_type else "Unknown"
        categories = ", ".join(category.display_name for category in (app.categories or [])) or "—"

        self._set_field("platform", platform)
        self._set_field("publisher", app.publisher)
        self._set_field("owner", app.owner)
        self._set_field("developer", app.developer)
        self._set_field(
            "created",
            app.created_date_time.strftime("%Y-%m-%d %H:%M") if app.created_date_time else None,
        )
        self._set_field(
            "modified",
            app.last_modified_date_time.strftime("%Y-%m-%d %H:%M") if app.last_modified_date_time else None,
        )
        self._set_field("categories", categories)

        self._assignments_list.clear()
        assignments = app.assignments or []
        if not assignments:
            placeholder = QListWidgetItem("No assignments cached.")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._assignments_list.addItem(placeholder)
        else:
            for assignment in assignments:
                target = getattr(assignment.target, "group_id", "All devices")
                intent = assignment.intent.value
                filter_id = getattr(assignment.target, "assignment_filter_id", None)
                text = f"{intent} → {target}"
                if filter_id:
                    text += f" (filter: {filter_id})"
                item = QListWidgetItem(text)
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                self._assignments_list.addItem(item)

        self.update_install_summary(None)
        self._set_icon(icon)

    def update_install_summary(self, summary: dict[str, object] | None) -> None:
        self._current_install_summary = summary
        self._install_summary_list.clear()
        if not summary:
            placeholder = QListWidgetItem("No install summary data loaded.")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._install_summary_list.addItem(placeholder)
            return

        for key, value in summary.items():
            item = QListWidgetItem(f"{key}: {value}")
            item.setData(Qt.ItemDataRole.UserRole, (key, value))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._install_summary_list.addItem(item)

    def _set_field(self, key: str, value: object | None) -> None:
        label = self._fields.get(key)
        if label:
            label.setText(_format_value(value))

    def _set_icon(self, icon: QIcon | None) -> None:
        if icon is None:
            pixmap = QPixmap(96, 96)
            pixmap.fill(Qt.GlobalColor.transparent)
            self._icon_label.setPixmap(pixmap)
            return
        self._icon_label.setPixmap(icon.pixmap(96, 96))

    def _clear_badges(self) -> None:
        while self._badge_layout.count():
            item = self._badge_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _update_badges(self, app: MobileApp) -> None:
        self._clear_badges()
        intents = {assignment.intent.value for assignment in (app.assignments or [])}
        if not intents:
            return
        for intent_key in sorted(intents):
            label_text, color = self._INTENT_BADGES.get(intent_key, (intent_key.title(), "#4b5563"))
            badge = QLabel(label_text)
            badge.setStyleSheet(
                "QLabel {"
                f"background-color: {color};"
                "color: white;"
                "padding: 2px 8px;"
                "border-radius: 10px;"
                "font-size: 11px;"
                "}"
            )
            self._badge_layout.addWidget(badge)
        self._badge_layout.addStretch()

    def _handle_install_summary_activated(self, item: QListWidgetItem) -> None:
        payload = item.data(Qt.ItemDataRole.UserRole)
        if not payload:
            return
        key, value = payload
        formatted = json.dumps(value, indent=2, default=str) if isinstance(value, (dict, list)) else str(value)
        dialog = QMessageBox(self)
        dialog.setWindowTitle(f"Install summary — {key}")
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setText(f"Entry '{key}'")
        dialog.setInformativeText("Inspect detailed payload below.")
        dialog.setDetailedText(formatted)
        dialog.exec()


class ApplicationsWidget(PageScaffold):
    """Managed applications workspace with assignment tooling."""

    def __init__(
        self,
        services: ServiceRegistry,
        *,
        context: UIContext,
        parent: QWidget | None = None,
    ) -> None:
        self._services = services
        self._context = context
        self._controller = ApplicationController(services)

        self._refresh_button = make_toolbar_button("Refresh", tooltip="Refresh applications from Microsoft Graph.")
        self._force_refresh_button = make_toolbar_button("Force refresh", tooltip="Refetch regardless of cache state.")
        self._install_summary_button = make_toolbar_button("Install summary", tooltip="Fetch install summary for selection.")
        self._cache_icon_button = make_toolbar_button("Fetch icon", tooltip="Cache application icon for selection.")
        self._edit_assignments_button = make_toolbar_button(
            "Edit assignments",
            tooltip="Open the assignment editor for the selected application.",
        )
        self._export_assignments_button = make_toolbar_button(
            "Export assignments",
            tooltip="Export current assignments to JSON.",
        )

        actions: List[QToolButton] = [
            self._refresh_button,
            self._force_refresh_button,
            self._install_summary_button,
            self._cache_icon_button,
            self._edit_assignments_button,
            self._export_assignments_button,
        ]

        super().__init__(
            "Applications",
            subtitle="Review managed applications, cache icons, and orchestrate assignment changes.",
            actions=actions,
            parent=parent,
        )

        self._model = ApplicationTableModel()
        self._proxy = ApplicationFilterProxyModel()
        self._proxy.setSourceModel(self._model)

        self._icon_cache: dict[str, QIcon] = {}
        self._install_summaries: dict[str, dict[str, object]] = {}
        self._selected_app: MobileApp | None = None
        self._command_unregister: Callable[[], None] | None = None

        self._model.set_icon_provider(lambda app_id: self._icon_cache.get(app_id))

        self._build_filters()
        self._build_body()

        self._refresh_button.clicked.connect(self._handle_refresh_clicked)
        self._force_refresh_button.clicked.connect(self._handle_force_refresh_clicked)
        self._install_summary_button.clicked.connect(self._handle_install_summary_clicked)
        self._cache_icon_button.clicked.connect(self._handle_cache_icon_clicked)
        self._edit_assignments_button.clicked.connect(self._handle_edit_assignments_clicked)
        self._export_assignments_button.clicked.connect(self._handle_export_assignments_clicked)

        self._controller.register_callbacks(
            refreshed=self._handle_apps_refreshed,
            error=self._handle_service_error,
            install_summary=self._handle_install_summary_event,
            icon_cached=self._handle_icon_cached,
        )

        self._register_commands()
        self._load_cached_apps()
        self._update_action_buttons()

        if self._services.applications is None:
            self._handle_service_unavailable()

        self.destroyed.connect(lambda *_: self._cleanup())

    # ----------------------------------------------------------------- UI setup

    def _build_filters(self) -> None:
        filters = QWidget()
        layout = QHBoxLayout(filters)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search applications, publishers…")
        self._search_input.textChanged.connect(self._handle_search_changed)
        layout.addWidget(self._search_input, stretch=2)

        self._platform_combo = QComboBox()
        self._platform_combo.currentIndexChanged.connect(self._handle_platform_changed)
        layout.addWidget(self._platform_combo)

        self._intent_combo = QComboBox()
        self._intent_combo.currentIndexChanged.connect(self._handle_intent_changed)
        layout.addWidget(self._intent_combo)

        self._summary_label = QLabel()
        self._summary_label.setStyleSheet("color: palette(mid);")
        layout.addWidget(self._summary_label, stretch=1)

        self.body_layout.addWidget(filters)

    def _build_body(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setSizes([680, 360])

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
        table_layout.addWidget(self._table)

        splitter.addWidget(table_container)

        self._detail_pane = ApplicationDetailPane(parent=splitter)
        splitter.addWidget(self._detail_pane)

        self.body_layout.addWidget(splitter, stretch=1)

        if selection_model := self._table.selectionModel():
            selection_model.selectionChanged.connect(self._handle_selection_changed)

        self._proxy.modelReset.connect(self._update_summary)
        self._proxy.rowsInserted.connect(lambda *_: self._update_summary())
        self._proxy.rowsRemoved.connect(lambda *_: self._update_summary())
        self._model.modelReset.connect(self._update_summary)

    # ---------------------------------------------------------------- Commands

    def _register_commands(self) -> None:
        action = CommandAction(
            id="applications.refresh",
            title="Refresh applications",
            callback=self._start_refresh,
            category="Applications",
            description="Refresh managed application catalog from Microsoft Graph.",
            shortcut="Ctrl+Shift+A",
        )
        self._command_unregister = self._context.command_registry.register(action)

    # ----------------------------------------------------------------- Data flow

    def _load_cached_apps(self) -> None:
        apps = self._controller.list_cached()
        self._model.set_apps(apps)
        self._apply_filter_options(apps)
        self._update_summary()
        if apps:
            self._table.selectRow(0)

    def _handle_apps_refreshed(
        self,
        apps: Iterable[MobileApp],
        from_cache: bool,
    ) -> None:
        apps_list = list(apps)
        selected_id = self._selected_app.id if self._selected_app else None
        self._model.set_apps(apps_list)
        self._apply_filter_options(apps_list)
        self._update_summary()
        if selected_id:
            self._reselect_app(selected_id)
        elif apps_list:
            self._table.selectRow(0)
        if not from_cache:
            self._context.show_notification(
                f"Loaded {len(apps_list):,} applications.",
                level=ToastLevel.SUCCESS,
            )
        self._context.clear_busy()
        self._refresh_button.setEnabled(True)
        self._force_refresh_button.setEnabled(True)

    def _handle_service_error(self, event: ServiceErrorEvent) -> None:
        self._context.clear_busy()
        self._refresh_button.setEnabled(True)
        self._force_refresh_button.setEnabled(True)
        self._context.show_notification(
            f"Application operation failed: {event.error}",
            level=ToastLevel.ERROR,
            duration_ms=8000,
        )

    def _handle_install_summary_event(self, event: InstallSummaryEvent) -> None:
        self._install_summaries[event.app_id] = event.summary
        if self._selected_app and self._selected_app.id == event.app_id:
            self._detail_pane.update_install_summary(event.summary)
        self._context.clear_busy()
        self._context.show_notification("Install summary refreshed.", level=ToastLevel.SUCCESS)

    def _handle_icon_cached(self, metadata: AttachmentMetadata) -> None:
        if metadata is None:
            return
        path = Path(metadata.path)
        if not path.exists():
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return
        icon = QIcon(pixmap)
        app_id = metadata.key.split(":")[0]
        self._icon_cache[app_id] = icon
        row_count = self._model.rowCount()
        if row_count > 0:
            top_left = self._model.index(0, 0)
            bottom_right = self._model.index(row_count - 1, 0)
            self._model.dataChanged.emit(
                top_left,
                bottom_right,
                [Qt.ItemDataRole.DecorationRole],
            )
        if self._selected_app and self._selected_app.id == app_id:
            self._detail_pane.display_app(self._selected_app, icon)

    # ----------------------------------------------------------------- Actions

    def _handle_refresh_clicked(self) -> None:
        self._start_refresh(force=False)

    def _handle_force_refresh_clicked(self) -> None:
        self._start_refresh(force=True)

    def _start_refresh(self, *, force: bool = False) -> None:
        if self._services.applications is None:
            self._context.show_notification(
                "Application service not configured. Configure tenant services to continue.",
                level=ToastLevel.WARNING,
            )
            return
        self._context.set_busy("Refreshing applications…")
        self._refresh_button.setEnabled(False)
        self._force_refresh_button.setEnabled(False)
        self._context.run_async(self._refresh_async(force=force))

    async def _refresh_async(self, *, force: bool) -> None:
        try:
            await self._controller.refresh(force=force)
        except Exception as exc:  # noqa: BLE001
            self._context.clear_busy()
            self._refresh_button.setEnabled(True)
            self._force_refresh_button.setEnabled(True)
            self._context.show_notification(
                f"Failed to refresh applications: {exc}",
                level=ToastLevel.ERROR,
            )

    def _handle_install_summary_clicked(self) -> None:
        app = self._selected_app
        if app is None:
            self._context.show_notification(
                "Select an application before requesting an install summary.",
                level=ToastLevel.WARNING,
            )
            return
        self._context.set_busy("Fetching install summary…")
        self._context.run_async(self._fetch_install_summary_async(app.id))

    async def _fetch_install_summary_async(self, app_id: str) -> None:
        try:
            await self._controller.fetch_install_summary(app_id)
        except Exception as exc:  # noqa: BLE001
            self._context.clear_busy()
            self._context.show_notification(
                f"Install summary failed: {exc}",
                level=ToastLevel.ERROR,
            )

    def _handle_cache_icon_clicked(self) -> None:
        app = self._selected_app
        if app is None:
            self._context.show_notification(
                "Select an application to fetch its icon.",
                level=ToastLevel.WARNING,
            )
            return
        self._context.set_busy("Caching icon…")
        self._context.run_async(self._cache_icon_async(app.id))

    async def _cache_icon_async(self, app_id: str) -> None:
        try:
            metadata = await self._controller.cache_icon(app_id, force=True)
            if metadata and metadata.path.exists():
                pixmap = QPixmap(str(metadata.path))
                if not pixmap.isNull():
                    icon = QIcon(pixmap)
                    self._icon_cache[app_id] = icon
                    if self._selected_app and self._selected_app.id == app_id:
                        self._detail_pane.display_app(self._selected_app, icon)
        except Exception as exc:  # noqa: BLE001
            self._context.show_notification(
                f"Failed to cache icon: {exc}",
                level=ToastLevel.ERROR,
            )
        finally:
            self._context.clear_busy()

    def _handle_edit_assignments_clicked(self) -> None:
        app = self._selected_app
        if app is None:
            self._context.show_notification(
                "Select an application before editing assignments.",
                level=ToastLevel.WARNING,
            )
            return
        if self._services.assignments is None:
            self._context.show_notification(
                "Assignment service not configured. Enable assignment workflows in Settings.",
                level=ToastLevel.WARNING,
            )
            return

        self._context.set_busy("Loading assignments…")
        self._context.run_async(self._open_assignment_editor_async(app))

    async def _open_assignment_editor_async(self, app: MobileApp) -> None:
        try:
            assignments = await self._controller.fetch_assignments(app.id)
        except Exception as exc:  # noqa: BLE001
            self._context.clear_busy()
            self._context.show_notification(
                f"Failed to load assignments: {exc}",
                level=ToastLevel.ERROR,
            )
            return

        groups: list[DirectoryGroup] = []
        filters: list[AssignmentFilter] = []
        if self._services.groups is not None:
            groups = self._services.groups.list_cached()
            if not groups:
                try:
                    groups = await self._services.groups.refresh(force=False)
                except Exception:  # noqa: BLE001
                    groups = []
        if self._services.assignment_filters is not None:
            filters = self._services.assignment_filters.list_cached()
            if not filters:
                try:
                    filters = await self._services.assignment_filters.refresh(force=False)
                except Exception:  # noqa: BLE001
                    filters = []

        self._context.clear_busy()
        dialog = AssignmentEditorDialog(
            app,
            assignments,
            groups,
            filters,
            on_export=lambda payload: self._export_assignments(payload, suggested_name=f"{app.display_name}_assignments.json"),
            parent=self,
        )
        if dialog.exec() == dialog.Accepted:
            desired = dialog.desired_assignments()
            diff = self._controller.diff_assignments(current=assignments, desired=desired)
            if diff is None or diff.is_noop:
                self._context.show_notification("No assignment changes detected.", level=ToastLevel.INFO)
                return
            if dialog.auto_export_enabled():
                self._export_assignments(desired, suggested_name=f"{app.display_name}_assignments_backup.json")
            self._context.set_busy("Applying assignment changes…")
            self._context.run_async(self._apply_assignment_diff_async(app.id, diff))

    async def _apply_assignment_diff_async(self, app_id: str, diff) -> None:  # type: ignore[valid-type]
        try:
            await self._controller.apply_diff(app_id, diff)
            self._context.show_notification(
                "Assignments updated successfully.",
                level=ToastLevel.SUCCESS,
            )
        except Exception as exc:  # noqa: BLE001
            self._context.show_notification(
                f"Failed to update assignments: {exc}",
                level=ToastLevel.ERROR,
                duration_ms=8000,
            )
        finally:
            self._context.clear_busy()

    def _handle_export_assignments_clicked(self) -> None:
        app = self._selected_app
        if app is None:
            self._context.show_notification(
                "Select an application before exporting assignments.",
                level=ToastLevel.WARNING,
            )
            return
        assignments = app.assignments or []
        if not assignments:
            self._context.show_notification("No assignments cached for export.", level=ToastLevel.INFO)
            return
        self._export_assignments(assignments, suggested_name=f"{app.display_name}_assignments.json")

    # ----------------------------------------------------------------- Filters

    def _handle_search_changed(self, text: str) -> None:
        self._proxy.set_search_text(text)
        self._update_summary()

    def _handle_platform_changed(self, index: int) -> None:  # noqa: ARG002
        platform = self._platform_combo.currentData()
        self._proxy.set_platform_filter(platform)
        self._update_summary()

    def _handle_intent_changed(self, index: int) -> None:  # noqa: ARG002
        intent = self._intent_combo.currentData()
        self._proxy.set_intent_filter(intent)
        self._update_summary()

    def _apply_filter_options(self, apps: Iterable[MobileApp]) -> None:
        platforms = sorted(
            {
                (app.platform_type.value if app.platform_type else "").strip()
                for app in apps
                if app.platform_type
            },
            key=lambda value: value.lower(),
        )
        intents = sorted(
            {
                assignment.intent.value
                for app in apps
                for assignment in (app.assignments or [])
            },
            key=lambda value: value.lower(),
        )
        self._populate_combo(self._platform_combo, "All platforms", platforms)
        self._populate_combo(self._intent_combo, "All intents", intents)

    def _populate_combo(self, combo: QComboBox, placeholder: str, values: List[str]) -> None:
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(placeholder, None)
        for value in values:
            combo.addItem(value or "Unknown", value or None)
        if current:
            index = combo.findData(current)
            combo.setCurrentIndex(index if index != -1 else 0)
        else:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)

    # ----------------------------------------------------------------- Selection

    def _handle_selection_changed(self, *_: object) -> None:
        selection_model = self._table.selectionModel()
        if selection_model is None:
            return
        indexes = selection_model.selectedRows()
        if not indexes:
            self._selected_app = None
            self._detail_pane.display_app(None, None)
            self._update_action_buttons()
            return
        proxy_index = indexes[0]
        source_index = self._proxy.mapToSource(proxy_index)
        app = self._model.app_at(source_index.row())
        self._selected_app = app
        icon = self._icon_cache.get(app.id) if app else None
        self._detail_pane.display_app(app, icon)
        if app:
            summary = self._install_summaries.get(app.id)
            self._detail_pane.update_install_summary(summary)
            if (
                self._services.applications is not None
                and app.id not in self._icon_cache
            ):
                self._context.run_async(self._cache_icon_async(app.id))
        self._update_action_buttons()

    def _reselect_app(self, app_id: str) -> None:
        for row in range(self._model.rowCount()):
            app = self._model.app_at(row)
            if app is None or app.id != app_id:
                continue
            proxy_index = self._proxy.mapFromSource(self._model.index(row, 0))
            if proxy_index.isValid():
                self._table.selectRow(proxy_index.row())
                self._table.scrollTo(proxy_index)
            break

    # ----------------------------------------------------------------- Helpers

    def _update_summary(self) -> None:
        total = self._model.rowCount()
        visible = self._proxy.rowCount()
        stale = self._services.applications is not None and self._controller.is_cache_stale()
        parts = [f"{visible:,} applications shown"]
        if visible != total:
            parts.append(f"{total:,} cached")
        if stale:
            parts.append("Cache stale — refresh recommended")
        self._summary_label.setText(" · ".join(parts))

    def _update_action_buttons(self) -> None:
        app_selected = self._selected_app is not None
        service_available = self._services.applications is not None
        assignment_service_available = self._services.assignments is not None

        for button in [self._install_summary_button, self._cache_icon_button]:
            button.setEnabled(service_available and app_selected)

        self._edit_assignments_button.setEnabled(
            service_available and assignment_service_available and app_selected,
        )
        self._export_assignments_button.setEnabled(service_available and app_selected)

        self._refresh_button.setEnabled(service_available)
        self._force_refresh_button.setEnabled(service_available)

    def _handle_service_unavailable(self) -> None:
        self._table.setEnabled(False)
        self._detail_pane.display_app(None, None)
        self._context.show_banner(
            "Application service unavailable — configure Microsoft Graph dependencies to continue.",
            level=ToastLevel.WARNING,
        )
        self._update_action_buttons()

    def _export_assignments(
        self,
        assignments: Iterable[MobileAppAssignment],
        *,
        suggested_name: str,
    ) -> None:
        if self._services.assignments is None:
            self._context.show_notification(
                "Assignment service not configured; export unavailable.",
                level=ToastLevel.WARNING,
            )
            return
        payload = self._controller.export_assignments(assignments)
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export assignments",
            suggested_name,
            "JSON files (*.json);;All files (*)",
        )
        if not filename:
            return
        try:
            with Path(filename).open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            self._context.show_notification("Assignments exported.", level=ToastLevel.SUCCESS)
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", f"Unable to write file: {exc}")

    def _cleanup(self) -> None:
        if self._command_unregister:
            try:
                self._command_unregister()
            except Exception:  # pragma: no cover - defensive unregister
                pass
            self._command_unregister = None
        self._controller.dispose()


__all__ = ["ApplicationsWidget"]
