from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QFileDialog,
    QDialog,
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

from intune_manager.config import SettingsManager
from intune_manager.data import (
    AttachmentMetadata,
    AssignmentFilter,
    DirectoryGroup,
    MobileApp,
    MobileAppAssignment,
)
from intune_manager.data.models.application import MobileAppPlatform
from intune_manager.data.models.assignment import (
    AssignmentIntent,
    GroupAssignmentTarget,
    AllDevicesAssignmentTarget,
    AllLicensedUsersAssignmentTarget,
    AssignmentTarget,
)
from intune_manager.services import ServiceErrorEvent, ServiceRegistry
from intune_manager.services.applications import InstallSummaryEvent
from intune_manager.services.assignments import AssignmentDiff
from intune_manager.graph.errors import AuthenticationError
from intune_manager.utils import (
    format_file_size,
    format_license_count,
    format_architecture,
    format_min_os,
)
from intune_manager.ui.components import (
    CommandAction,
    InlineStatusMessage,
    PageScaffold,
    ToastLevel,
    UIContext,
    format_relative_timestamp,
    make_toolbar_button,
)
from intune_manager.utils.app_types import (
    PLATFORM_TYPE_COMPATIBILITY,
    get_display_name,
    is_compatible,
)
from intune_manager.utils.enums import enum_text
from intune_manager.utils.errors import ErrorSeverity, describe_exception

from intune_manager.ui.assignments.assignment_editor import AssignmentEditorDialog
from .controller import ApplicationController
from .models import ApplicationFilterProxyModel, ApplicationTableModel
from .bulk_assignment import (
    BulkAssignmentDialog,
    BulkAssignmentPlan,
    ALL_DEVICES_ID,
    ALL_USERS_ID,
)


def _toast_level_for(severity: ErrorSeverity) -> ToastLevel:
    try:
        return ToastLevel(severity.value)
    except ValueError:  # pragma: no cover - defensive mapping fallback
        return ToastLevel.ERROR


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
        self._icon_label.setStyleSheet(
            "border: 1px solid palette(midlight); border-radius: 12px;"
        )
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
        self._title_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self._subtitle_label = QLabel("")
        self._subtitle_label.setWordWrap(True)
        self._subtitle_label.setStyleSheet("color: palette(mid);")
        self._subtitle_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

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
        self._description_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        overview_layout.addWidget(self._description_label)

        form_group = QGroupBox("Metadata")
        self._metadata_form_layout = QFormLayout(form_group)
        self._metadata_form_layout.setContentsMargins(12, 8, 12, 8)
        self._metadata_form_layout.setSpacing(6)
        # Fields will be added dynamically based on app type
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
        self._assignments_list.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        assignments_layout.addWidget(self._assignments_list, stretch=1)

        # Install status tab
        self._install_tab = QWidget()
        install_layout = QVBoxLayout(self._install_tab)
        install_layout.setContentsMargins(0, 0, 0, 0)
        install_layout.setSpacing(6)
        install_hint = QLabel(
            "Fetch install summaries to review deployment cohorts and drill into raw payloads."
        )
        install_hint.setWordWrap(True)
        install_hint.setStyleSheet("color: palette(mid);")
        install_layout.addWidget(install_hint)
        self._install_summary_list = QListWidget()
        self._install_summary_list.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        self._install_summary_list.itemActivated.connect(
            self._handle_install_summary_activated
        )
        install_layout.addWidget(self._install_summary_list, stretch=1)

        self._tab_widget.addTab(self._overview_tab, "Overview")
        self._tab_widget.addTab(self._assignments_tab, "Assignments")
        self._tab_widget.addTab(self._install_tab, "Install status")

        self._current_install_summary: dict[str, object] | None = None
        self._on_install_tab_selected: Callable[[], None] | None = None
        self._current_app_id: str | None = None

        # Connect tab change signal to handle auto-fetch
        self._tab_widget.currentChanged.connect(self._handle_tab_changed)

    # ----------------------------------------------------------------- Tab callback

    def set_install_tab_callback(self, callback: Callable[[], None] | None) -> None:
        """Set callback to be invoked when Install status tab is selected."""
        self._on_install_tab_selected = callback

    def _handle_tab_changed(self, index: int) -> None:
        """Handle tab selection changes."""
        # Index 2 is the "Install status" tab
        if index == 2 and self._current_install_summary is None:
            if self._on_install_tab_selected is not None:
                self._on_install_tab_selected()

    # ----------------------------------------------------------------- Metadata helpers

    def _clear_metadata_fields(self) -> None:
        """Remove all rows from metadata form layout."""
        while self._metadata_form_layout.rowCount() > 0:
            self._metadata_form_layout.removeRow(0)

    def _add_metadata_field(self, label: str, value: str | None) -> None:
        """Add a single field to metadata form.

        Args:
            label: Field label (e.g., "Platform")
            value: Field value or None for "—"
        """
        value_label = QLabel(value if value else "—")
        value_label.setWordWrap(True)
        value_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._metadata_form_layout.addRow(f"{label}:", value_label)

    def _populate_metadata_fields(self, app: MobileApp) -> None:
        """Populate metadata fields dynamically based on app type."""
        self._clear_metadata_fields()

        # Base fields (always shown)
        platform = enum_text(app.platform_type) or "Unknown"
        categories = (
            ", ".join(category.display_name for category in (app.categories or []))
            or None
        )
        created = (
            app.created_date_time.strftime("%Y-%m-%d %H:%M")
            if app.created_date_time
            else None
        )
        modified = (
            app.last_modified_date_time.strftime("%Y-%m-%d %H:%M")
            if app.last_modified_date_time
            else None
        )

        self._add_metadata_field("Platform", platform)
        self._add_metadata_field("Publisher", app.publisher)
        self._add_metadata_field("Owner", app.owner)
        self._add_metadata_field("Developer", app.developer)
        self._add_metadata_field("Created", created)
        self._add_metadata_field("Modified", modified)
        self._add_metadata_field("Categories", categories)

        # Assignment & Scope fields
        if app.is_assigned is not None:
            self._add_metadata_field("Is Assigned", "Yes" if app.is_assigned else "No")
        if app.role_scope_tag_ids:
            scope_tags = ", ".join(app.role_scope_tag_ids)
            self._add_metadata_field("Scope Tags", scope_tags)

        # Platform-specific fields
        if app.platform_type == MobileAppPlatform.IOS:
            if app.app_type == "VPP":
                self._add_ios_vpp_fields(app)
            elif app.app_type == "LOB":
                self._add_lob_fields(app)
        elif app.platform_type == MobileAppPlatform.WINDOWS:
            if app.app_type == "LOB":
                self._add_windows_lob_fields(app)
            elif app.app_type == "Win32":
                self._add_win32_fields(app)
            else:
                self._add_windows_fields(app)
        elif app.platform_type == MobileAppPlatform.ANDROID:
            if app.app_type == "LOB":
                self._add_android_lob_fields(app)

        # Generic LOB fields (if not already added by platform-specific methods)
        if app.app_type == "LOB" and app.platform_type not in (
            MobileAppPlatform.IOS,
            MobileAppPlatform.WINDOWS,
            MobileAppPlatform.ANDROID,
        ):
            self._add_lob_fields(app)

    def _add_ios_vpp_fields(self, app: MobileApp) -> None:
        """Add iOS VPP-specific fields."""
        if app.bundle_id:
            self._add_metadata_field("Bundle ID", app.bundle_id)
        if app.used_license_count is not None or app.total_license_count is not None:
            license_info = format_license_count(
                app.used_license_count, app.total_license_count
            )
            self._add_metadata_field("License Usage", license_info)
        if app.vpp_token_display_name or app.vpp_token_organization_name:
            token_name = app.vpp_token_display_name or app.vpp_token_organization_name
            self._add_metadata_field("VPP Token", token_name)
        if app.vpp_token_account_type:
            self._add_metadata_field(
                "VPP Account Type", app.vpp_token_account_type.capitalize()
            )
        if app.app_store_url:
            self._add_metadata_field("App Store URL", app.app_store_url)

    def _add_lob_fields(self, app: MobileApp) -> None:
        """Add generic LOB app fields."""
        if app.file_name:
            self._add_metadata_field("File Name", app.file_name)
        if app.size is not None:
            size_str = format_file_size(app.size)
            self._add_metadata_field("Size", size_str)
        if app.committed_content_version:
            self._add_metadata_field("Content Version", app.committed_content_version)

    def _add_windows_lob_fields(self, app: MobileApp) -> None:
        """Add Windows LOB-specific fields."""
        self._add_lob_fields(app)  # Include common LOB fields
        self._add_windows_fields(app)  # Include Windows-specific fields

    def _add_windows_fields(self, app: MobileApp) -> None:
        """Add Windows app-specific fields."""
        if app.applicable_architectures:
            arch_str = format_architecture(app.applicable_architectures)
            self._add_metadata_field("Architecture", arch_str)
        if app.identity_name:
            self._add_metadata_field("Identity Name", app.identity_name)
        if app.minimum_supported_operating_system:
            min_os = format_min_os(app.minimum_supported_operating_system)
            self._add_metadata_field("Minimum OS", min_os)

    def _add_win32_fields(self, app: MobileApp) -> None:
        """Add Win32-specific fields."""
        self._add_lob_fields(app)  # Include common LOB fields
        if app.setup_file_path:
            self._add_metadata_field("Setup File", app.setup_file_path)
        if app.minimum_supported_windows_release:
            self._add_metadata_field(
                "Min Windows Release", app.minimum_supported_windows_release
            )
        if app.display_version:
            self._add_metadata_field("Display Version", app.display_version)

    def _add_android_lob_fields(self, app: MobileApp) -> None:
        """Add Android LOB-specific fields."""
        self._add_lob_fields(app)  # Include common LOB fields
        if app.package_id:
            self._add_metadata_field("Package ID", app.package_id)
        if app.version_name:
            self._add_metadata_field("Version Name", app.version_name)
        if app.version_code:
            self._add_metadata_field("Version Code", app.version_code)

    # ----------------------------------------------------------------- Display methods

    def display_app(
        self,
        app: MobileApp | None,
        icon: QIcon | None,
        *,
        groups: list[DirectoryGroup] | None = None,
        filters: list[AssignmentFilter] | None = None,
    ) -> None:
        if app is None:
            self._title_label.setText("Select an application")
            self._subtitle_label.setText("")
            self._description_label.setText("")
            self._clear_badges()
            self._set_icon(icon)
            self._clear_metadata_fields()
            self._assignments_list.clear()
            self.update_install_summary(None)
            self._current_app_id = None
            return

        self._current_app_id = app.id

        self._title_label.setText(app.display_name)
        subtitle_parts = [app.owner or "", app.publisher or ""]
        self._subtitle_label.setText(
            " · ".join(part for part in subtitle_parts if part)
        )
        self._description_label.setText(app.description or "")
        self._update_badges(app)

        # Populate metadata fields dynamically based on app type
        self._populate_metadata_fields(app)

        # Build lookup dictionaries for groups and filters
        group_lookup = {g.id: g for g in (groups or []) if g.id}
        filter_lookup = {f.id: f for f in (filters or []) if f.id}

        self._assignments_list.clear()
        assignments = app.assignments or []
        if not assignments:
            placeholder = QListWidgetItem("No assignments cached.")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._assignments_list.addItem(placeholder)
        else:
            for assignment in assignments:
                # Get target display name
                group_id = getattr(assignment.target, "group_id", None)
                if group_id:
                    group = group_lookup.get(group_id)
                    if group:
                        target = (
                            group.display_name
                            or group.mail
                            or group.mail_nickname
                            or group_id
                        )
                    else:
                        target = group_id
                else:
                    target = "All devices"

                intent = enum_text(assignment.intent) or "Unknown"
                text = f"{intent} → {target}"

                # Add filter information
                filter_id = getattr(assignment.target, "assignment_filter_id", None)
                filter_type = getattr(assignment.target, "assignment_filter_type", None)
                if filter_id:
                    # Get filter display name
                    assignment_filter = filter_lookup.get(filter_id)
                    filter_name = (
                        assignment_filter.display_name
                        if assignment_filter and assignment_filter.display_name
                        else filter_id
                    )

                    filter_type_str = enum_text(filter_type) if filter_type else ""
                    mode_labels = {
                        "none": "",
                        "include": "Include",
                        "exclude": "Exclude",
                    }
                    mode = mode_labels.get(filter_type_str.lower(), filter_type_str)
                    if mode:
                        text += f" ({mode}: {filter_name})"
                    else:
                        text += f" (Filter: {filter_name})"

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
        intents = {
            enum_text(assignment.intent) or "unknown"
            for assignment in (app.assignments or [])
        }
        if not intents:
            return
        for intent_key in sorted(intents):
            label_text, color = self._INTENT_BADGES.get(
                intent_key, (intent_key.title(), "#4b5563")
            )
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
        formatted = (
            json.dumps(value, indent=2, default=str)
            if isinstance(value, (dict, list))
            else str(value)
        )
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

        self._refresh_button = make_toolbar_button(
            "Refresh", tooltip="Refresh applications from Microsoft Graph."
        )
        self._force_refresh_button = make_toolbar_button(
            "Force refresh", tooltip="Refetch regardless of cache state."
        )
        self._install_summary_button = make_toolbar_button(
            "Install summary", tooltip="Fetch install summary for selection."
        )
        self._edit_assignments_button = make_toolbar_button(
            "Edit assignments",
            tooltip="Open the assignment editor for the selected application.",
        )
        self._export_assignments_button = make_toolbar_button(
            "Export assignments",
            tooltip="Export current assignments to JSON.",
        )
        self._bulk_assign_button = make_toolbar_button(
            "Bulk assign",
            tooltip="Assign multiple applications to selected groups in one workflow.",
        )
        self._bulk_assign_button.setEnabled(False)

        actions: List[QToolButton] = [
            self._refresh_button,
            self._force_refresh_button,
            self._install_summary_button,
            self._edit_assignments_button,
            self._bulk_assign_button,
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
        self._lazy_threshold = 800
        self._lazy_chunk_size = 300
        self._pending_selection_id: str | None = None
        self._last_refresh: datetime | None = None
        self._model.load_finished.connect(self._handle_model_load_finished)
        self._model.batch_appended.connect(lambda *_: self._update_summary())

        self._icon_cache: dict[str, QIcon] = {}
        self._install_summaries: dict[str, dict[str, object]] = {}
        self._selected_app: MobileApp | None = None
        self._selected_apps: list[MobileApp] = []
        self._command_unregister: Callable[[], None] | None = None
        self._cached_groups: list[DirectoryGroup] = []
        self._cached_filters: list[AssignmentFilter] = []
        self._auth_warning_shown = False
        settings = SettingsManager().load()
        self._tenant_id = settings.tenant_id if settings else None

        # Filter message label for showing incompatibility warnings
        self._filter_message = QLabel()
        self._filter_message.setStyleSheet(
            "QLabel { background-color: #FFF3CD; color: #856404; "
            "padding: 8px 12px; border-radius: 4px; border: 1px solid #FFE69C; }"
        )
        self._filter_message.setWordWrap(True)
        self._filter_message.setVisible(False)

        self._model.set_icon_provider(lambda app_id: self._icon_cache.get(app_id))

        self._build_filters()
        self._build_body()

        self._refresh_button.clicked.connect(self._handle_refresh_clicked)
        self._force_refresh_button.clicked.connect(self._handle_force_refresh_clicked)
        self._install_summary_button.clicked.connect(
            self._handle_install_summary_clicked
        )
        self._edit_assignments_button.clicked.connect(
            self._handle_edit_assignments_clicked
        )
        self._export_assignments_button.clicked.connect(
            self._handle_export_assignments_clicked
        )
        self._bulk_assign_button.clicked.connect(self._handle_bulk_assign_clicked)

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

    def _active_tenant_id(self) -> str | None:
        """Resolve the current tenant ID from settings (cached for convenience)."""

        settings = SettingsManager().load()
        if settings and settings.tenant_id:
            self._tenant_id = settings.tenant_id
        return self._tenant_id

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

        self._type_combo = QComboBox()
        self._type_combo.currentIndexChanged.connect(self._handle_type_changed)
        layout.addWidget(self._type_combo)

        self._intent_combo = QComboBox()
        self._intent_combo.currentIndexChanged.connect(self._handle_intent_changed)
        layout.addWidget(self._intent_combo)

        self._summary_label = QLabel()
        self._summary_label.setStyleSheet("color: palette(mid);")
        self._summary_label.setToolTip("No refresh recorded yet.")
        layout.addWidget(self._summary_label, stretch=1)

        self.body_layout.addWidget(filters)
        self.body_layout.addWidget(self._filter_message)

    def _build_body(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setSizes([680, 360])

        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)

        self._list_message = InlineStatusMessage(parent=table_container)
        table_layout.addWidget(self._list_message)

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table_layout.addWidget(self._table)

        splitter.addWidget(table_container)

        self._detail_pane = ApplicationDetailPane(parent=splitter)
        self._detail_pane.set_install_tab_callback(self._auto_fetch_install_summary)
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

    def focus_search(self) -> None:
        self._search_input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._search_input.selectAll()

    # ----------------------------------------------------------------- Data flow

    def _load_cached_apps(self) -> None:
        self._list_message.clear()
        tenant_id = self._active_tenant_id()
        apps = list(self._controller.list_cached(tenant_id=tenant_id))
        self._last_refresh = self._controller.last_refresh(tenant_id=tenant_id)
        self._set_apps_for_view(
            apps,
            preserve_selection=self._selected_app.id if self._selected_app else None,
        )
        if apps:
            self._context.run_async(
                self._background_fetch_icons_async(apps, tenant_id=tenant_id)
            )
        self._load_groups_and_filters()

    def _load_groups_and_filters(self) -> None:
        """Load groups and filters for assignment display."""
        if self._services.groups is not None:
            self._cached_groups = self._services.groups.list_cached()
        if self._services.assignment_filters is not None:
            self._cached_filters = self._services.assignment_filters.list_cached()

    def _handle_apps_refreshed(
        self,
        apps: Iterable[MobileApp],
        from_cache: bool,
    ) -> None:
        self._list_message.clear()
        self._auth_warning_shown = False
        apps_list = list(apps)
        selected_id = self._selected_app.id if self._selected_app else None
        self._last_refresh = self._controller.last_refresh()
        self._set_apps_for_view(apps_list, preserve_selection=selected_id)
        self._load_groups_and_filters()
        if not from_cache:
            self._context.show_notification(
                f"Loaded {len(apps_list):,} applications.",
                level=ToastLevel.SUCCESS,
            )
        self._context.clear_busy()
        self._refresh_button.setEnabled(True)
        self._force_refresh_button.setEnabled(True)

        # Trigger background icon fetching for all apps
        if apps_list:
            self._context.run_async(
                self._background_fetch_icons_async(
                    apps_list, tenant_id=self._active_tenant_id()
                )
            )

    def _set_apps_for_view(
        self,
        apps_list: list[MobileApp],
        *,
        preserve_selection: str | None = None,
    ) -> None:
        if len(apps_list) > self._lazy_threshold:
            self._pending_selection_id = preserve_selection
            self._model.set_apps_lazy(apps_list, chunk_size=self._lazy_chunk_size)
        else:
            self._pending_selection_id = None
            self._model.set_apps(apps_list)
            if preserve_selection:
                self._reselect_app(preserve_selection)
            elif apps_list:
                self._table.selectRow(0)
        self._apply_filter_options(apps_list)
        self._update_summary()

    def _handle_model_load_finished(self) -> None:
        if self._pending_selection_id:
            self._reselect_app(self._pending_selection_id)
        elif self._model.rowCount() > 0 and not self._selected_app:
            self._table.selectRow(0)
        self._pending_selection_id = None
        self._update_summary()

    def _handle_service_error(self, event: ServiceErrorEvent) -> None:
        self._context.clear_busy()
        self._refresh_button.setEnabled(True)
        self._force_refresh_button.setEnabled(True)
        if isinstance(event.error, AuthenticationError):
            if not self._auth_warning_shown:
                self._list_message.display(
                    "Sign in required to load applications.",
                    level=ToastLevel.WARNING,
                    detail="Your Intune session expired. Open Settings and run Test sign-in to continue.",
                )
                self._context.show_notification(
                    "Authentication required. Open Settings to sign in.",
                    level=ToastLevel.WARNING,
                    duration_ms=6000,
                )
                self._auth_warning_shown = True
            return
        descriptor = describe_exception(event.error)
        detail_lines = [descriptor.detail]
        if descriptor.transient:
            detail_lines.append("This issue appears transient. Retry in a moment.")
        if descriptor.suggestion:
            detail_lines.append(f"Suggested action: {descriptor.suggestion}")
        detail_text = "\n\n".join(detail_lines)
        level = _toast_level_for(descriptor.severity)
        self._list_message.display(descriptor.headline, level=level, detail=detail_text)
        toast_message = descriptor.headline
        if descriptor.transient:
            toast_message = f"{descriptor.headline} Retry after a short wait."
        self._context.show_notification(
            toast_message,
            level=level,
            duration_ms=8000,
        )

    def _handle_install_summary_event(self, event: InstallSummaryEvent) -> None:
        self._install_summaries[event.app_id] = event.summary
        if self._selected_app and self._selected_app.id == event.app_id:
            self._detail_pane.update_install_summary(event.summary)
        self._context.clear_busy()
        self._context.show_notification(
            "Install summary refreshed.", level=ToastLevel.SUCCESS
        )

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
            self._detail_pane.display_app(
                self._selected_app,
                icon,
                groups=self._cached_groups,
                filters=self._cached_filters,
            )

    # ----------------------------------------------------------------- Actions

    def _handle_refresh_clicked(self) -> None:
        self._start_refresh(force=False)

    def _handle_force_refresh_clicked(self) -> None:
        self._start_refresh(force=True)

    def _start_refresh(self, *, force: bool = False) -> None:
        if self._services.applications is None:
            self._list_message.display(
                "Application service unavailable. Configure Microsoft Graph dependencies to refresh the catalog.",
                level=ToastLevel.WARNING,
            )
            self._context.show_notification(
                "Application service not configured. Configure tenant services to continue.",
                level=ToastLevel.WARNING,
            )
            return
        self._list_message.clear()
        self._context.set_busy("Refreshing applications…", blocking=False)
        self._refresh_button.setEnabled(False)
        self._force_refresh_button.setEnabled(False)
        self._context.run_async(self._refresh_async(force=force))

    async def _refresh_async(self, *, force: bool) -> None:
        try:
            tenant_id = self._active_tenant_id()
            await self._controller.refresh(tenant_id=tenant_id, force=force)
        except Exception as exc:  # noqa: BLE001
            descriptor = describe_exception(exc)
            detail_lines = [descriptor.detail]
            if descriptor.transient:
                detail_lines.append("This issue may be temporary. Retry in a moment.")
            if descriptor.suggestion:
                detail_lines.append(f"Suggested action: {descriptor.suggestion}")
            detail_text = "\n\n".join(detail_lines)
            level = _toast_level_for(descriptor.severity)
            self._list_message.display(
                descriptor.headline, level=level, detail=detail_text
            )
            if descriptor.transient:
                toast_message = f"{descriptor.headline} Retry after a short wait."
            else:
                toast_message = f"Failed to refresh applications: {exc}"
            self._context.show_notification(
                toast_message,
                level=level,
            )
        finally:
            self._context.clear_busy()
            self._refresh_button.setEnabled(True)
            self._force_refresh_button.setEnabled(True)
            self._update_action_buttons()

    def _handle_install_summary_clicked(self) -> None:
        app = self._selected_app
        if app is None:
            self._context.show_notification(
                "Select an application before requesting an install summary.",
                level=ToastLevel.WARNING,
            )
            return
        force_refresh = bool(
            QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier
        )
        if app.id:
            cached = self._install_summaries.get(app.id)
        else:
            cached = None
        if cached and not force_refresh:
            self._detail_pane.update_install_summary(cached)
            self._context.show_notification(
                "Install summary loaded from cache. Hold Shift and click to force a refresh.",
                level=ToastLevel.INFO,
            )
            return
        self._context.set_busy("Fetching install summary…")
        self._context.run_async(
            self._fetch_install_summary_async(app.id, force=force_refresh)
        )

    async def _fetch_install_summary_async(
        self, app_id: str, *, force: bool = False
    ) -> None:
        try:
            await self._controller.fetch_install_summary(app_id, force=force)
        except Exception as exc:  # noqa: BLE001
            self._context.clear_busy()
            self._context.show_notification(
                f"Install summary failed: {exc}",
                level=ToastLevel.ERROR,
            )

    def _auto_fetch_install_summary(self) -> None:
        """Auto-fetch install summary when Install status tab is selected."""
        app = self._selected_app
        if app is None or not app.id:
            return
        if self._services.applications is None:
            return

        # Check in-memory cache first
        cached = self._install_summaries.get(app.id)
        if cached:
            self._detail_pane.update_install_summary(cached)
            return

        # Fetch from service
        self._context.set_busy("Fetching install summary…", blocking=False)
        self._context.run_async(self._fetch_install_summary_async(app.id, force=False))

    async def _background_fetch_icons_async(
        self, apps: list[MobileApp], *, tenant_id: str | None = None
    ) -> None:
        """Fetch icons in background for all apps without blocking UI."""
        try:
            await self._controller.background_fetch_icons(apps, tenant_id=tenant_id)
        except Exception as exc:  # noqa: BLE001
            # Silently log background fetch failures
            from intune_manager.utils import get_logger

            logger = get_logger(__name__)
            logger.debug("Background icon fetch failed", error=str(exc))

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
        self._context.run_async(self._fetch_assignment_data_async(app))

    async def _fetch_assignment_data_async(self, app: MobileApp) -> None:
        """Fetch all data needed for assignment editor asynchronously."""
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
                    filters = await self._services.assignment_filters.refresh(
                        force=False
                    )
                except Exception:  # noqa: BLE001
                    filters = []

        self._context.clear_busy()
        # Schedule dialog opening in Qt event loop (breaks out of async context)
        QTimer.singleShot(
            0,
            lambda: self._open_assignment_editor_dialog(
                app, assignments, groups, filters
            ),
        )

    def _open_assignment_editor_dialog(
        self,
        app: MobileApp,
        assignments: list[MobileAppAssignment],
        groups: list[DirectoryGroup],
        filters: list[AssignmentFilter],
    ) -> None:
        """Open assignment editor dialog with pre-fetched data (synchronous)."""
        subject = app.display_name or app.id or "Application"
        try:
            dialog = AssignmentEditorDialog(
                assignments=assignments,
                groups=groups,
                filters=filters,
                subject_name=subject,
                on_export=lambda payload: self._export_assignments(
                    payload, suggested_name=f"{subject}_assignments.json"
                ),
                parent=self,
            )
        except Exception as exc:  # noqa: BLE001
            error_msg = describe_exception(exc)
            self._context.show_notification(
                f"Failed to open assignment editor: {error_msg}",
                level=ToastLevel.ERROR,
            )
            return

        if dialog.exec() == QDialog.DialogCode.Accepted:
            desired = dialog.desired_assignments()
            diff = self._controller.diff_assignments(
                current=assignments, desired=desired
            )
            if diff is None or diff.is_noop:
                self._context.show_notification(
                    "No assignment changes detected.", level=ToastLevel.INFO
                )
                return
            if dialog.auto_export_enabled():
                self._export_assignments(
                    desired,
                    suggested_name=f"{app.display_name}_assignments_backup.json",
                )
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

    def _handle_bulk_assign_clicked(self) -> None:
        if not self._selected_apps:
            self._context.show_notification(
                "Select one or more applications before using bulk assignment.",
                level=ToastLevel.INFO,
            )
            return
        if self._services.assignments is None:
            self._context.show_notification(
                "Assignment service not configured. Enable assignment workflows in Settings.",
                level=ToastLevel.WARNING,
            )
            return

        # Load active tenant_id for cache consistency
        settings_manager = SettingsManager()
        settings = settings_manager.load()
        tenant_id = settings.tenant_id if settings else None

        group_service = self._services.groups
        if group_service is None:
            self._context.show_notification(
                "Group service unavailable. Refresh directory groups before applying assignments.",
                level=ToastLevel.WARNING,
            )
            return
        groups = [
            group
            for group in group_service.list_cached(tenant_id=tenant_id)
            if group.id
        ]
        if not groups:
            # Auto-refresh groups and retry
            self._context.show_notification(
                "No groups cached. Refreshing now...",
                level=ToastLevel.INFO,
            )
            self._context.set_busy("Refreshing groups…")
            self._context.run_async(
                self._refresh_groups_and_open_bulk_assign_async(
                    group_service, tenant_id
                )
            )
            return

        self._open_bulk_assign_dialog(groups, tenant_id)

    def _open_bulk_assign_dialog(
        self, groups: list[DirectoryGroup], tenant_id: str | None
    ) -> None:
        """Open the bulk assignment dialog with the given groups."""
        filters_service = self._services.assignment_filters
        filters = filters_service.list_cached() if filters_service is not None else []

        dialog = BulkAssignmentDialog(
            apps=self._selected_apps,
            groups=groups,
            filters=filters,
            parent=self,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        plan = dialog.plan()
        if plan is None:
            return

        self._context.set_busy("Applying bulk assignments…")
        self._refresh_button.setEnabled(False)
        self._force_refresh_button.setEnabled(False)
        self._bulk_assign_button.setEnabled(False)
        self._context.run_async(self._apply_bulk_assignments_async(plan))

    async def _refresh_groups_and_open_bulk_assign_async(
        self, group_service, tenant_id: str | None
    ) -> None:
        """Refresh groups from Graph API and open bulk assignment dialog if successful."""
        try:
            await group_service.refresh(tenant_id=tenant_id, force=True)
            groups = [
                group
                for group in group_service.list_cached(tenant_id=tenant_id)
                if group.id
            ]
            if groups:
                self._context.show_notification(
                    f"Loaded {len(groups):,} groups.",
                    level=ToastLevel.SUCCESS,
                )
                self._open_bulk_assign_dialog(groups, tenant_id)
            else:
                self._context.show_notification(
                    "No groups available. Ensure your account has permission to read groups.",
                    level=ToastLevel.WARNING,
                )
        except Exception as exc:  # noqa: BLE001
            self._context.show_notification(
                f"Failed to refresh groups: {exc}",
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
            self._context.show_notification(
                "No assignments cached for export.", level=ToastLevel.INFO
            )
            return
        self._export_assignments(
            assignments, suggested_name=f"{app.display_name}_assignments.json"
        )

    async def _apply_bulk_assignments_async(self, plan: BulkAssignmentPlan) -> None:
        total_apps = len(plan.apps)
        if total_apps == 0 or not plan.groups:
            return

        self._context.set_busy("Applying assignments to selected apps…")
        failures: list[str] = []
        applied = 0

        try:
            app_diffs: list[tuple[str, AssignmentDiff]] = []
            for app in plan.apps:
                current_assignments = list(app.assignments or [])
                desired_assignments = list(current_assignments)
                updated = False
                for group in plan.groups:
                    if not group.id:
                        continue
                    target_type = "#microsoft.graph.groupAssignmentTarget"
                    target_group_id: str | None = group.id
                    if group.id == ALL_DEVICES_ID:
                        target_type = "#microsoft.graph.allDevicesAssignmentTarget"
                        target_group_id = None
                    elif group.id == ALL_USERS_ID:
                        target_type = (
                            "#microsoft.graph.allLicensedUsersAssignmentTarget"
                        )
                        target_group_id = None
                    existing = self._find_assignment(
                        current_assignments,
                        target_group_id,
                        plan.filter_id,
                        plan.intent,
                        target_type=target_type,
                    )
                    if existing:
                        if (
                            plan.settings is not None
                            and existing.settings != plan.settings
                        ):
                            replacement = existing.model_copy(
                                update={"settings": plan.settings}
                            )
                            desired_assignments = [
                                replacement if assignment is existing else assignment
                                for assignment in desired_assignments
                            ]
                            updated = True
                        continue
                    target: AssignmentTarget
                    if group.id == ALL_DEVICES_ID:
                        target = AllDevicesAssignmentTarget(
                            assignment_filter_id=plan.filter_id,
                            assignment_filter_type=plan.filter_mode,
                        )
                    elif group.id == ALL_USERS_ID:
                        target = AllLicensedUsersAssignmentTarget(
                            assignment_filter_id=plan.filter_id,
                            assignment_filter_type=plan.filter_mode,
                        )
                    else:
                        target = GroupAssignmentTarget(
                            group_id=group.id,
                            assignment_filter_id=plan.filter_id,
                            assignment_filter_type=plan.filter_mode,
                        )
                    new_assignment = MobileAppAssignment.model_construct(
                        id="",
                        intent=plan.intent,
                        target=target,
                        settings=plan.settings,
                    )
                    desired_assignments.append(new_assignment)
                    updated = True
                if not updated:
                    continue
                diff = self._controller.diff_assignments(
                    current=current_assignments,
                    desired=desired_assignments,
                )
                if diff is None or diff.is_noop:
                    continue
                app_diffs.append((app.id, diff))

            if not app_diffs:
                self._context.show_notification(
                    "No assignment changes were necessary.",
                    level=ToastLevel.INFO,
                    duration_ms=4000,
                )
                return

            try:
                await self._controller.apply_diffs(app_diffs)
                applied = len(app_diffs)
            except Exception as exc:  # noqa: BLE001
                failures.append(str(exc))

            if applied:
                await self._controller.refresh(force=True, include_assignments=True)
        finally:
            self._context.clear_busy()
            self._refresh_button.setEnabled(True)
            self._force_refresh_button.setEnabled(True)
            self._update_action_buttons()

        if failures:
            self._context.show_notification(
                f"Assignments applied with {len(failures)} failure(s). Check logs for details.",
                level=ToastLevel.WARNING,
                duration_ms=8000,
            )
        elif applied:
            self._context.show_notification(
                f"Assignments applied to {applied} application(s).",
                level=ToastLevel.SUCCESS,
            )

    @staticmethod
    def _find_assignment(
        assignments: Iterable[MobileAppAssignment],
        group_id: str | None,
        filter_id: str | None,
        intent: AssignmentIntent,
        target_type: str | None = None,
    ) -> MobileAppAssignment | None:
        for assignment in assignments:
            if assignment.intent != intent:
                continue
            target = assignment.target
            if target_type and getattr(target, "odata_type", None) != target_type:
                continue
            if group_id is not None:
                target_group = getattr(target, "group_id", None)
                if target_group != group_id:
                    continue
            target_filter = getattr(target, "assignment_filter_id", None)
            if (filter_id or None) != (target_filter or None):
                continue
            return assignment
        return None

    # ----------------------------------------------------------------- Filters

    def _handle_search_changed(self, text: str) -> None:
        self._proxy.set_search_text(text)
        self._update_summary()
        self._check_filter_compatibility()

    def _handle_platform_changed(self, index: int) -> None:  # noqa: ARG002
        platform = self._platform_combo.currentData()
        self._proxy.set_platform_filter(platform)
        self._update_summary()
        self._check_filter_compatibility()

    def _handle_type_changed(self, index: int) -> None:  # noqa: ARG002
        app_type = self._type_combo.currentData()
        self._proxy.set_type_filter(app_type)
        self._update_summary()
        self._check_filter_compatibility()

    def _handle_intent_changed(self, index: int) -> None:  # noqa: ARG002
        intent = self._intent_combo.currentData()
        self._proxy.set_intent_filter(intent)
        self._update_summary()

    def _check_filter_compatibility(self) -> None:
        """Check if platform and type filters are compatible, show message if not."""
        platform = self._platform_combo.currentData()
        app_type = self._type_combo.currentData()

        # If no filters, hide message
        if not platform and not app_type:
            self._filter_message.setVisible(False)
            return

        # Check if filters result in zero rows
        row_count = self._proxy.rowCount()

        if row_count == 0 and (platform or app_type):
            # Check if it's due to incompatibility
            if platform and app_type and not is_compatible(platform, app_type):
                # Get display name for the selected type
                type_text = self._type_combo.currentText()
                platform_display = {
                    "ios": "iOS",
                    "macos": "macOS",
                    "windows": "Windows",
                    "android": "Android",
                }.get(platform.lower(), platform.title())

                self._filter_message.setText(
                    f"⚠️  No results: {type_text} apps are not available for {platform_display} platform. "
                    "Choose a compatible combination or clear filters to see all apps."
                )
                self._filter_message.setVisible(True)
            elif platform or app_type or self._search_input.text():
                # Filters are applied but just no matching results
                self._filter_message.setText(
                    "ℹ️  No apps match the current filters. Try adjusting your search or filter criteria."
                )
                self._filter_message.setVisible(True)
            else:
                self._filter_message.setVisible(False)
        else:
            # Results found or no filters
            self._filter_message.setVisible(False)

    def _apply_filter_options(self, apps: Iterable[MobileApp]) -> None:
        # Get all available platforms from enum (show all, not just those with data)
        all_platforms = [
            p.value for p in MobileAppPlatform if p != MobileAppPlatform.UNKNOWN
        ]

        # Get platforms that actually have apps in the cache
        platforms_with_data = {
            (enum_text(app.platform_type) or "").strip()
            for app in apps
            if app.platform_type and app.platform_type != MobileAppPlatform.UNKNOWN
        }

        # Populate platform combo with all known platforms
        self._populate_combo_with_disabled(
            self._platform_combo, "All platforms", all_platforms, platforms_with_data
        )

        # Extract all platform+type combinations from apps
        platform_type_combinations = {}  # key: (platform, type), value: count
        platforms_present: set[str] = set()
        for app in apps:
            platform = enum_text(app.platform_type) or ""
            app_type = app.app_type or ""
            if platform and app_type:
                key = (platform, app_type)
                platform_type_combinations[key] = (
                    platform_type_combinations.get(key, 0) + 1
                )
            if platform:
                platforms_present.add(platform.lower())

        # Seed combinations for platforms we have data for, so picker shows all known types
        for platform in platforms_present:
            for app_type, supported_platforms in PLATFORM_TYPE_COMPATIBILITY.items():
                if platform in supported_platforms:
                    key = (
                        {
                            "ios": "iOS",
                            "macos": "macOS",
                            "windows": "Windows",
                            "android": "Android",
                        }.get(platform, platform.title()),
                        app_type,
                    )
                    platform_type_combinations.setdefault(key, 0)

        # Create display names for type filter
        type_options = []
        type_data = []
        for (platform, app_type), count in sorted(platform_type_combinations.items()):
            display = get_display_name(platform, app_type)
            type_options.append(display)
            type_data.append(app_type)

        # Populate type combo (all items have data by construction)
        self._populate_combo(self._type_combo, "All types", type_options, type_data)

        # Extract intents
        intents = sorted(
            {
                enum_text(assignment.intent) or ""
                for app in apps
                for assignment in (app.assignments or [])
            },
            key=lambda value: value.lower(),
        )
        self._populate_combo(self._intent_combo, "All intents", intents)

    def _populate_combo(
        self,
        combo: QComboBox,
        placeholder: str,
        values: List[str],
        data: List[str] | None = None,
    ) -> None:
        """Populate combo box with values and optional custom data."""
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(placeholder, None)
        for i, value in enumerate(values):
            # Use custom data if provided, otherwise use value itself
            item_data = data[i] if data and i < len(data) else (value or None)
            combo.addItem(value or "Unknown", item_data)
        if current:
            index = combo.findData(current)
            combo.setCurrentIndex(index if index != -1 else 0)
        else:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _populate_combo_with_disabled(
        self,
        combo: QComboBox,
        placeholder: str,
        all_values: List[str],
        enabled_values: set[str],
    ) -> None:
        """Populate combo box with all values, disabling those not in enabled_values."""
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(placeholder, None)

        for value in sorted(all_values, key=lambda v: v.lower()):
            combo.addItem(value or "Unknown", value or None)
            # Disable if not in enabled_values
            if value not in enabled_values:
                index = combo.count() - 1
                # Use gray color for disabled items
                model = combo.model()
                if model:
                    item = model.item(index)
                    if item:
                        item.setEnabled(False)

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
            self._selected_apps = []
            self._detail_pane.display_app(None, None)
            self._detail_pane.update_install_summary(None)
            self._update_action_buttons()
            return
        selected_apps: list[MobileApp] = []
        for proxy_index in indexes:
            source_index = self._proxy.mapToSource(proxy_index)
            app = self._model.app_at(source_index.row())
            if app is None:
                continue
            selected_apps.append(app)
        self._selected_apps = selected_apps
        self._selected_app = selected_apps[0] if selected_apps else None

        if self._selected_app is None:
            self._detail_pane.display_app(None, None)
            self._detail_pane.update_install_summary(None)
        else:
            app = self._selected_app
            icon = self._icon_cache.get(app.id) if app.id else None
            self._detail_pane.display_app(
                app, icon, groups=self._cached_groups, filters=self._cached_filters
            )
            summary = self._install_summaries.get(app.id)
            self._detail_pane.update_install_summary(summary)
        self._update_action_buttons()
        self._update_summary()

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
        stale = (
            self._services.applications is not None
            and self._controller.is_cache_stale()
        )
        parts = [f"{visible:,} applications shown"]
        if visible != total:
            parts.append(f"{total:,} cached")
        if stale:
            parts.append("Cache stale — refresh recommended")
        if self._selected_apps:
            parts.append(f"{len(self._selected_apps):,} selected")
        if self._last_refresh:
            parts.append(f"Updated {format_relative_timestamp(self._last_refresh)}")
            tooltip = (
                f"Last refresh: {self._last_refresh.strftime('%Y-%m-%d %H:%M:%S')} UTC"
            )
        else:
            parts.append("Never refreshed")
            tooltip = "No refresh recorded yet."
        self._summary_label.setToolTip(tooltip)
        self._summary_label.setText(" · ".join(parts))

    def _update_action_buttons(self) -> None:
        app_selected = self._selected_app is not None
        multiple_selected = len(self._selected_apps) > 1
        any_selected = bool(self._selected_apps)
        service_available = self._services.applications is not None
        assignment_service_available = self._services.assignments is not None

        self._install_summary_button.setEnabled(
            service_available and app_selected and not multiple_selected
        )

        self._edit_assignments_button.setEnabled(
            service_available
            and assignment_service_available
            and app_selected
            and not multiple_selected,
        )
        self._export_assignments_button.setEnabled(
            service_available and app_selected and not multiple_selected
        )
        self._bulk_assign_button.setEnabled(
            service_available and assignment_service_available and any_selected,
        )

        self._refresh_button.setEnabled(service_available)
        self._force_refresh_button.setEnabled(service_available)

    def _handle_service_unavailable(self) -> None:
        self._table.setEnabled(False)
        self._detail_pane.display_app(None, None)
        self._list_message.display(
            "Application service unavailable. Configure Microsoft Graph dependencies to load applications.",
            level=ToastLevel.WARNING,
        )
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
            self._context.show_notification(
                "Assignments exported.", level=ToastLevel.SUCCESS
            )
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
