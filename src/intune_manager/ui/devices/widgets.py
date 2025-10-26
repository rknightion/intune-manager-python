from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import Iterable, List

from PySide6.QtCore import QItemSelectionModel, QModelIndex, QPoint, Qt
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QSplitter,
    QStackedLayout,
    QTableView,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QMenu,
)

from intune_manager.data import ManagedDevice
from intune_manager.graph.requests import DeviceActionName
from intune_manager.services import ServiceErrorEvent, ServiceRegistry
from intune_manager.services.devices import (
    DeviceActionEvent,
    DeviceRefreshProgressEvent,
)
from intune_manager.ui.components import (
    CommandAction,
    InlineStatusMessage,
    PageScaffold,
    ProgressDialog,
    ToastLevel,
    UIContext,
    format_relative_timestamp,
    make_toolbar_button,
)
from intune_manager.utils import (
    CancellationError,
    CancellationTokenSource,
    ProgressUpdate,
)
from intune_manager.utils.errors import ErrorSeverity, describe_exception

from .controller import DeviceController
from .delegates import ComplianceBadgeDelegate, DeviceSummaryDelegate
from .models import DeviceFilterProxyModel, DeviceTableModel, DeviceTimelineEntry
from intune_manager.utils.enums import enum_text


def _format_value(value: object | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _format_bytes(value: int | None) -> str:
    if value is None:
        return "—"
    if value <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(value)
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    if index == 0:
        return f"{int(size)} {units[index]}"
    return f"{size:.1f} {units[index]}"


def _toast_level_for(severity: ErrorSeverity) -> ToastLevel:
    try:
        return ToastLevel(severity.value)
    except ValueError:  # pragma: no cover - defensive mapping fallback
        return ToastLevel.ERROR


class DeviceDetailCache:
    """Simple LRU cache to provide instant detail pane rendering."""

    def __init__(self, capacity: int = 2048) -> None:
        self._capacity = max(1, capacity)
        self._entries: OrderedDict[str, ManagedDevice] = OrderedDict()

    def clear(self) -> None:
        self._entries.clear()

    def prime(self, devices: Iterable[ManagedDevice]) -> None:
        for device in devices:
            self.put(device)

    def put(self, device: ManagedDevice) -> None:
        if not device.id:
            return
        key = device.id
        if key in self._entries:
            self._entries.pop(key)
        self._entries[key] = device
        while len(self._entries) > self._capacity:
            self._entries.popitem(last=False)

    def get(self, device_id: str | None) -> ManagedDevice | None:
        if not device_id:
            return None
        device = self._entries.get(device_id)
        if device is not None:
            self._entries.move_to_end(device_id)
        return device


class DeviceDetailPane(QWidget):
    """Right-hand pane displaying selected device information with tabbed insights."""

    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._stack = QStackedLayout(self)

        self._empty_state = QWidget()
        empty_layout = QVBoxLayout(self._empty_state)
        empty_layout.setContentsMargins(24, 24, 24, 24)
        empty_layout.addStretch()
        self._empty_label = QLabel(
            "Select a device to inspect compliance, hardware health, and installed applications.",
            parent=self._empty_state,
        )
        self._empty_label.setWordWrap(True)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self._empty_label)
        empty_layout.addStretch()
        self._stack.addWidget(self._empty_state)

        self._detail_widget = QWidget()
        detail_layout = QVBoxLayout(self._detail_widget)
        detail_layout.setContentsMargins(16, 16, 16, 16)
        detail_layout.setSpacing(12)

        self._title_label = QLabel()
        title_font = self._title_label.font()
        title_font.setPointSizeF(title_font.pointSizeF() + 2)
        title_font.setWeight(QFont.Weight.DemiBold)
        self._title_label.setFont(title_font)

        self._subtitle_label = QLabel()
        self._subtitle_label.setWordWrap(True)
        self._subtitle_label.setStyleSheet("color: palette(mid);")

        detail_layout.addWidget(self._title_label)
        detail_layout.addWidget(self._subtitle_label)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.setTabPosition(QTabWidget.TabPosition.North)

        overview_fields = [
            ("user", "Primary user"),
            ("ownership", "Ownership"),
            ("compliance", "Compliance"),
            ("management", "Management"),
            ("enrollment", "Enrollment type"),
            ("registration", "Registration state"),
            ("category", "Category"),
            ("last_sync", "Last sync"),
            ("enrolled", "Enrolled on"),
        ]
        hardware_fields = [
            ("manufacturer", "Manufacturer"),
            ("model", "Model"),
            ("chassis", "Chassis"),
            ("serial", "Serial"),
            ("sku", "SKU"),
            ("storage_total", "Total storage"),
            ("storage_free", "Free storage"),
            ("memory", "Physical memory"),
            ("battery_health", "Battery health"),
            ("battery_level", "Battery level"),
        ]
        network_fields = [
            ("azure_id", "Azure AD device ID"),
            ("ip_v4", "IP address (v4)"),
            ("wifi_mac", "Wi-Fi MAC"),
            ("ethernet_mac", "Ethernet MAC"),
            ("imei", "IMEI"),
            ("meid", "MEID"),
            ("udid", "UDID"),
        ]
        security_fields = [
            ("azure_registered", "Azure AD registered"),
            ("encrypted", "Encrypted"),
            ("supervised", "Supervised"),
            ("jailbroken", "Jailbreak detection"),
            ("lost_mode", "Lost mode"),
            ("threat_state", "Threat state"),
            ("dfci_managed", "DFCI managed"),
            ("bootstrap", "Bootstrap escrowed"),
        ]

        self._overview_tab, self._overview_fields = self._create_form_tab(
            overview_fields
        )
        self._hardware_tab, self._hardware_fields = self._create_form_tab(
            hardware_fields
        )
        self._network_tab, self._network_fields = self._create_form_tab(network_fields)
        self._security_tab, self._security_fields = self._create_form_tab(
            security_fields
        )

        self._tabs.addTab(self._overview_tab, "Overview")
        self._tabs.addTab(self._hardware_tab, "Hardware")
        self._tabs.addTab(self._network_tab, "Network")
        self._tabs.addTab(self._security_tab, "Security")

        self._apps_widget = QWidget()
        apps_layout = QVBoxLayout(self._apps_widget)
        apps_layout.setContentsMargins(0, 8, 0, 0)
        apps_layout.setSpacing(6)

        self._apps_summary = QLabel()
        self._apps_summary.setStyleSheet("color: palette(mid);")
        apps_layout.addWidget(self._apps_summary)

        self._apps_list = QListWidget()
        self._apps_list.setObjectName("InstalledAppsList")
        self._apps_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        apps_layout.addWidget(self._apps_list, stretch=1)

        self._tabs.addTab(self._apps_widget, "Installed Apps")

        self._timeline_widget = QWidget()
        timeline_layout = QVBoxLayout(self._timeline_widget)
        timeline_layout.setContentsMargins(0, 8, 0, 0)
        timeline_layout.setSpacing(6)

        self._timeline_status = QLabel(
            "Device actions, audit events, and applied policies appear here when available."
        )
        self._timeline_status.setWordWrap(True)
        self._timeline_status.setStyleSheet("color: palette(mid);")
        timeline_layout.addWidget(self._timeline_status)

        self._timeline_list = QListWidget()
        self._timeline_list.setObjectName("DeviceTimelineList")
        self._timeline_list.setAlternatingRowColors(True)
        self._timeline_list.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        self._timeline_list.setUniformItemSizes(False)
        timeline_layout.addWidget(self._timeline_list, stretch=1)

        self._tabs.addTab(self._timeline_widget, "Timeline")

        detail_layout.addWidget(self._tabs, stretch=1)
        self._stack.addWidget(self._detail_widget)

    # ----------------------------------------------------------------- Helpers

    def show_placeholder(self, message: str) -> None:
        self._empty_label.setText(message)
        self._stack.setCurrentWidget(self._empty_state)
        self.set_timeline([], error="Select a device to view timeline.")

    def set_timeline(
        self,
        entries: Iterable[DeviceTimelineEntry],
        *,
        loading: bool = False,
        error: str | None = None,
    ) -> None:
        self._timeline_list.clear()
        if loading:
            self._timeline_status.setText(
                "Fetching device history from Microsoft Graph…"
            )
            placeholder = QListWidgetItem("Loading timeline…")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._timeline_list.addItem(placeholder)
            return
        if error:
            self._timeline_status.setText(error)
            placeholder = QListWidgetItem("Timeline unavailable.")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._timeline_list.addItem(placeholder)
            return
        entries_list = list(entries)
        if not entries_list:
            self._timeline_status.setText(
                "No historical activity found for this device."
            )
            placeholder = QListWidgetItem("No timeline events.")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._timeline_list.addItem(placeholder)
            return

        self._timeline_status.setText(
            "Latest audit and management events for this device."
        )
        for entry in entries_list:
            timestamp = entry.formatted_timestamp()
            lines = [f"{timestamp} — {entry.title}"]
            details: list[str] = []
            if entry.description and entry.description != entry.title:
                details.append(entry.description)
            if entry.actor:
                details.append(f"Actor: {entry.actor}")
            if entry.result:
                details.append(f"Result: {entry.result}")
            if entry.category:
                details.append(f"Category: {entry.category}")
            text = "\n".join(lines + details)
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            tooltip_lines = [entry.title]
            if entry.description and entry.description != entry.title:
                tooltip_lines.append(entry.description)
            if entry.actor:
                tooltip_lines.append(f"Actor: {entry.actor}")
            if entry.result:
                tooltip_lines.append(f"Result: {entry.result}")
            item.setToolTip("\n".join(tooltip_lines))
            self._timeline_list.addItem(item)

    def focus_overview(self) -> None:
        self._tabs.setCurrentWidget(self._overview_tab)

    def display_device(self, device: ManagedDevice | None) -> None:
        if device is None:
            self._stack.setCurrentWidget(self._empty_state)
            return

        self._stack.setCurrentWidget(self._detail_widget)
        self._title_label.setText(device.device_name)
        subtitle_parts = [
            device.manufacturer or "",
            device.model or "",
            f"Serial: {device.serial_number}" if device.serial_number else "",
        ]
        subtitle = " · ".join(part for part in subtitle_parts if part)
        self._subtitle_label.setText(subtitle or "No hardware metadata available.")

        self._set_fields(
            self._overview_fields,
            {
                "user": device.user_display_name or device.user_principal_name,
                "ownership": enum_text(device.ownership),
                "compliance": enum_text(device.compliance_state),
                "management": enum_text(device.management_state),
                "enrollment": device.enrolled_managed_by,
                "registration": device.device_registration_state,
                "category": device.device_category_display_name,
                "last_sync": self._format_datetime(device.last_sync_date_time),
                "enrolled": self._format_datetime(device.enrolled_date_time),
            },
        )
        self._set_fields(
            self._hardware_fields,
            {
                "manufacturer": device.manufacturer,
                "model": device.model,
                "chassis": device.chassis_type,
                "serial": device.serial_number,
                "sku": f"{device.sku_family or '—'} {device.sku_number or ''}".strip(),
                "storage_total": _format_bytes(device.total_storage_space_in_bytes),
                "storage_free": _format_bytes(device.free_storage_space_in_bytes),
                "memory": _format_bytes(device.physical_memory_in_bytes),
                "battery_health": f"{device.battery_health_percentage} %"
                if device.battery_health_percentage is not None
                else None,
                "battery_level": f"{device.battery_level_percentage:.0f} %"
                if device.battery_level_percentage is not None
                else None,
            },
        )
        self._set_fields(
            self._network_fields,
            {
                "azure_id": device.azure_ad_device_id,
                "ip_v4": device.ip_address_v4,
                "wifi_mac": device.wi_fi_mac_address,
                "ethernet_mac": device.ethernet_mac_address,
                "imei": device.imei,
                "meid": device.meid,
                "udid": device.udid,
            },
        )
        self._set_fields(
            self._security_fields,
            {
                "azure_registered": device.azure_ad_registered,
                "encrypted": device.is_encrypted,
                "supervised": device.is_supervised,
                "jailbroken": device.jailbreak_detection_state,
                "lost_mode": device.lost_mode_state,
                "threat_state": device.partner_reported_threat_state,
                "dfci_managed": device.device_firmware_configuration_interface_managed,
                "bootstrap": device.bootstrap_token_escrowed,
            },
        )

        self._populate_apps(device)

    def _create_form_tab(
        self,
        fields: list[tuple[str, str]],
    ) -> tuple[QWidget, dict[str, QLabel]]:
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        labels: dict[str, QLabel] = {}
        for key, label in fields:
            value_label = QLabel("—")
            value_label.setWordWrap(True)
            labels[key] = value_label
            layout.addRow(f"{label}:", value_label)
        return widget, labels

    def _set_fields(
        self, mapping: dict[str, QLabel], values: dict[str, object | None]
    ) -> None:
        for key, value in values.items():
            label = mapping.get(key)
            if label is None:
                continue
            label.setText(_format_value(value))

    def _populate_apps(self, device: ManagedDevice) -> None:
        self._apps_list.clear()
        apps = device.installed_apps or []
        if not apps:
            self._apps_summary.setText("Installed applications: inventory not loaded.")
            placeholder = QListWidgetItem(
                "No installed applications reported for this device."
            )
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._apps_list.addItem(placeholder)
            return

        self._apps_summary.setText(f"Installed applications: {len(apps):,}")
        for app in sorted(apps, key=lambda item: (item.display_name or "").lower()):
            name = app.display_name or "Unknown application"
            version = app.version or "—"
            publisher = app.publisher or ""
            text = f"{name} ({version})"
            if publisher:
                text += f" — {publisher}"
            item = QListWidgetItem(text)
            tooltip_parts = [
                f"Install state: {app.install_state or 'unknown'}",
            ]
            if app.last_sync_date_time:
                tooltip_parts.append(f"Last sync: {app.last_sync_date_time}")
            item.setToolTip("\n".join(tooltip_parts))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._apps_list.addItem(item)

    @staticmethod
    def _format_datetime(value: datetime | None) -> str:
        if value is None:
            return "—"
        return value.strftime("%Y-%m-%d %H:%M")


class DevicesWidget(PageScaffold):
    """Device management workspace with searchable grid and detail pane."""

    _ACTION_LABELS: dict[DeviceActionName, str] = {
        "syncDevice": "Sync",
        "retire": "Retire",
        "wipe": "Wipe",
        "rebootNow": "Reboot",
        "shutDown": "Shutdown",
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
        self._controller = DeviceController(services)
        self._detail_cache = DeviceDetailCache()
        self._total_devices = 0
        self._pending_selection_ids: set[str] = set()
        self._auto_select_first = False
        self._lazy_threshold = 1000
        self._lazy_chunk_size = 400
        self._refresh_token_source: CancellationTokenSource | None = None
        self._refresh_progress_dialog: ProgressDialog | None = None
        self._refresh_in_progress = False
        self._last_refresh: datetime | None = None

        self._refresh_button = make_toolbar_button(
            "Refresh",
            tooltip="Refresh devices from Microsoft Graph when cache is stale.",
        )
        self._force_refresh_button = make_toolbar_button(
            "Force refresh",
            tooltip="Bypass cache checks and fetch the latest devices immediately.",
        )
        self._sync_device_button = make_toolbar_button(
            "Sync",
            tooltip="Trigger an Intune sync for the selected device.",
        )
        self._wipe_button = make_toolbar_button(
            "Wipe",
            tooltip="Issue a wipe request for the selected device.",
        )
        self._retire_button = make_toolbar_button(
            "Retire",
            tooltip="Retire the selected device from management.",
        )
        self._reboot_button = make_toolbar_button(
            "Reboot",
            tooltip="Reboot the selected device.",
        )
        self._shutdown_button = make_toolbar_button(
            "Shutdown",
            tooltip="Shut down the selected device.",
        )
        self._export_button = make_toolbar_button(
            "Export",
            tooltip="Export the selected devices to CSV.",
        )
        self._export_button.setEnabled(False)

        self._copy_button = make_toolbar_button(
            "Copy details",
            tooltip="Copy selected device details to the clipboard.",
        )
        self._copy_button.setEnabled(False)

        actions: List[QToolButton] = [
            self._refresh_button,
            self._force_refresh_button,
            self._export_button,
            self._copy_button,
            self._sync_device_button,
            self._retire_button,
            self._wipe_button,
            self._reboot_button,
            self._shutdown_button,
        ]

        super().__init__(
            "Devices",
            subtitle="Search managed devices, inspect health signals, and execute management actions.",
            actions=actions,
            parent=parent,
        )

        self._model = DeviceTableModel()
        self._proxy = DeviceFilterProxyModel()
        self._proxy.setSourceModel(self._model)
        self._model.load_finished.connect(self._handle_model_loaded)
        self._model.batch_appended.connect(self._handle_model_batch_appended)

        self._selected_devices: list[ManagedDevice] = []
        self._selected_device_ids: set[str] = set()
        self._pending_actions = 0
        self._bulk_action_active = False
        self._bulk_action_summary: dict[str, int | str] | None = None
        self._command_unregister: Callable[[], None] | None = None
        self._active_timeline_device_id: str | None = None
        self._table_delegates: list[object] = []
        self._table_delegates.clear()

        self._build_filters()
        self._build_body()

        self._refresh_button.clicked.connect(self._handle_refresh_clicked)
        self._force_refresh_button.clicked.connect(self._handle_force_refresh_clicked)
        self._sync_device_button.clicked.connect(
            lambda: self._handle_device_action("syncDevice")
        )
        self._retire_button.clicked.connect(
            lambda: self._handle_device_action("retire")
        )
        self._wipe_button.clicked.connect(lambda: self._handle_device_action("wipe"))
        self._reboot_button.clicked.connect(
            lambda: self._handle_device_action("rebootNow")
        )
        self._shutdown_button.clicked.connect(
            lambda: self._handle_device_action("shutDown")
        )
        self._export_button.clicked.connect(self._handle_export_selected)
        self._copy_button.clicked.connect(self._handle_copy_selected_devices)

        self._controller.register_callbacks(
            refreshed=self._handle_devices_refreshed,
            error=self._handle_service_error,
            action=self._handle_action_event,
            progress=self._handle_refresh_progress,
        )

        self._register_commands()
        self._load_cached_devices()
        self._update_action_buttons()

        if self._services.devices is None:
            self._handle_service_unavailable()

        self.destroyed.connect(lambda *_: self._cleanup())

    # ----------------------------------------------------------------- UI setup

    def _build_filters(self) -> None:
        self._filters_widget = QWidget()
        layout = QHBoxLayout(self._filters_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search devices, users, serials…")
        self._search_input.textChanged.connect(self._handle_search_changed)
        layout.addWidget(self._search_input, stretch=2)

        self._platform_combo = QComboBox()
        self._platform_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._platform_combo.currentIndexChanged.connect(self._handle_platform_changed)
        layout.addWidget(self._platform_combo)

        self._compliance_combo = QComboBox()
        self._compliance_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._compliance_combo.currentIndexChanged.connect(
            self._handle_compliance_changed
        )
        layout.addWidget(self._compliance_combo)

        self._management_combo = QComboBox()
        self._management_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._management_combo.currentIndexChanged.connect(
            self._handle_management_changed
        )
        layout.addWidget(self._management_combo)

        self._ownership_combo = QComboBox()
        self._ownership_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._ownership_combo.currentIndexChanged.connect(
            self._handle_ownership_changed
        )
        layout.addWidget(self._ownership_combo)

        self._enrollment_combo = QComboBox()
        self._enrollment_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._enrollment_combo.currentIndexChanged.connect(
            self._handle_enrollment_changed
        )
        layout.addWidget(self._enrollment_combo)

        self._threat_combo = QComboBox()
        self._threat_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._threat_combo.currentIndexChanged.connect(self._handle_threat_changed)
        layout.addWidget(self._threat_combo)

        self._summary_label = QLabel()
        self._summary_label.setObjectName("DeviceSummaryLabel")
        self._summary_label.setStyleSheet("color: palette(mid);")
        self._summary_label.setToolTip("No refresh recorded yet.")
        layout.addWidget(self._summary_label, stretch=1)

        self.body_layout.addWidget(self._filters_widget)

    def _build_body(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setSizes([700, 340])

        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)

        self._list_message = InlineStatusMessage(parent=table_container)
        table_layout.addWidget(self._list_message)

        self._table = QTableView()
        self._table.setObjectName("DeviceTable")
        self._table.setModel(self._proxy)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(48)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.setWordWrap(False)

        device_column = self._model.column_index("device_name")
        if device_column is not None:
            device_delegate = DeviceSummaryDelegate(parent=self._table)
            self._table.setItemDelegateForColumn(device_column, device_delegate)
            self._table_delegates.append(device_delegate)

        compliance_column = self._model.column_index("compliance_state")
        if compliance_column is not None:
            compliance_delegate = ComplianceBadgeDelegate(parent=self._table)
            self._table.setItemDelegateForColumn(compliance_column, compliance_delegate)
            self._table_delegates.append(compliance_delegate)

        table_layout.addWidget(self._table)

        splitter.addWidget(table_container)

        self._detail_pane = DeviceDetailPane(parent=splitter)
        splitter.addWidget(self._detail_pane)

        self.body_layout.addWidget(splitter, stretch=1)

        if selection_model := self._table.selectionModel():
            selection_model.selectionChanged.connect(self._handle_selection_changed)

        self._proxy.rowsInserted.connect(lambda *_: self._update_summary())
        self._proxy.rowsRemoved.connect(lambda *_: self._update_summary())
        self._proxy.modelReset.connect(self._update_summary)
        self._model.modelReset.connect(self._update_summary)

    # ---------------------------------------------------------------- Commands

    def _register_commands(self) -> None:
        action = CommandAction(
            id="devices.refresh",
            title="Refresh devices",
            callback=self._start_refresh,
            category="Devices",
            description="Pull the latest managed devices from Microsoft Graph.",
            shortcut="Ctrl+Shift+D",
        )
        self._command_unregister = self._context.command_registry.register(action)

    def focus_search(self) -> None:
        self._search_input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._search_input.selectAll()

    # ----------------------------------------------------------------- Data flow

    def _handle_model_batch_appended(self, _: int) -> None:
        self._update_summary()

    def _handle_model_loaded(self) -> None:
        if self._pending_selection_ids:
            self._reselect_devices(self._pending_selection_ids)
        elif self._auto_select_first and self._model.rowCount() > 0:
            self._table.selectRow(0)
        self._pending_selection_ids = set()
        self._auto_select_first = False
        self._update_summary()

    def _set_devices_for_view(
        self,
        devices: Iterable[ManagedDevice],
        *,
        preserve_selection: set[str] | None = None,
        auto_select_first: bool = True,
    ) -> None:
        self._list_message.clear()
        device_list = list(devices)
        self._total_devices = len(device_list)
        self._detail_cache.clear()
        self._detail_cache.prime(device_list)
        self._apply_filter_options(device_list)

        if self._total_devices > self._lazy_threshold:
            self._pending_selection_ids = set(preserve_selection or [])
            self._auto_select_first = auto_select_first
            self._model.set_devices_lazy(device_list, chunk_size=self._lazy_chunk_size)
        else:
            self._pending_selection_ids = set()
            self._auto_select_first = False
            self._model.set_devices(device_list)
            if preserve_selection:
                self._reselect_devices(preserve_selection)
            elif auto_select_first and device_list:
                self._table.selectRow(0)

        if not device_list:
            self._detail_pane.show_placeholder(
                "No managed devices cached. Refresh to load the latest inventory.",
            )

        self._update_summary()

    def _load_cached_devices(self) -> None:
        devices = self._controller.list_cached()
        self._last_refresh = self._controller.last_refresh()
        self._set_devices_for_view(devices, auto_select_first=True)

    def _handle_devices_refreshed(
        self,
        devices: Iterable[ManagedDevice],
        from_cache: bool,
    ) -> None:
        self._finish_refresh(mark_finished=True)
        devices_list = list(devices)
        previous_ids = set(self._selected_device_ids)
        auto_select_first = not previous_ids
        self._last_refresh = self._controller.last_refresh()
        self._set_devices_for_view(
            devices_list,
            preserve_selection=previous_ids,
            auto_select_first=auto_select_first,
        )
        if not from_cache:
            self._context.show_notification(
                f"Loaded {len(devices_list):,} devices from Microsoft Graph.",
                level=ToastLevel.SUCCESS,
            )

    def _handle_service_error(self, event: ServiceErrorEvent) -> None:
        self._finish_refresh()
        descriptor = describe_exception(event.error)
        detail_lines = [descriptor.detail]
        if descriptor.transient:
            detail_lines.append(
                "This issue appears to be transient. Retry after a short wait."
            )
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

    def _handle_action_event(self, event: DeviceActionEvent) -> None:
        label = self._ACTION_LABELS.get(event.action, event.action.title())
        if self._bulk_action_active and self._bulk_action_summary is not None:
            if event.success:
                self._bulk_action_summary["success"] += 1
            else:
                self._bulk_action_summary["failure"] += 1
                detail = str(event.error) if event.error else "Unknown error"
                self._context.show_notification(
                    f"{label} failed for {event.device_id}: {detail}",
                    level=ToastLevel.ERROR,
                    duration_ms=8000,
                )
            processed = (
                self._bulk_action_summary["success"]
                + self._bulk_action_summary["failure"]
            )
            total = self._bulk_action_summary["total"]
            remaining = max(total - processed, 0)
            self._context.set_busy(
                f"{label} in progress… {processed}/{total} processed (remaining {remaining})",
            )
        else:
            if event.success:
                self._context.show_notification(
                    f"{label} sent to device {event.device_id}",
                    level=ToastLevel.SUCCESS,
                )
            else:
                detail = str(event.error) if event.error else "Unknown error"
                self._context.show_notification(
                    f"{label} failed for device {event.device_id}: {detail}",
                    level=ToastLevel.ERROR,
                    duration_ms=8000,
                )

        if self._pending_actions > 0:
            self._pending_actions -= 1
            if self._pending_actions < 0:
                self._pending_actions = 0

        if self._pending_actions == 0:
            if self._bulk_action_active and self._bulk_action_summary is not None:
                summary = self._bulk_action_summary
                total = summary["total"]
                successes = summary["success"]
                failures = summary["failure"]
                level = ToastLevel.SUCCESS if failures == 0 else ToastLevel.WARNING
                message = f"{summary['label']} completed for {total} device(s): {successes} success, {failures} failed."
                self._context.show_notification(message, level=level, duration_ms=6000)
            self._bulk_action_active = False
            self._bulk_action_summary = None
            self._context.clear_busy()
            self._update_action_buttons()

    def _handle_refresh_progress(self, event: DeviceRefreshProgressEvent) -> None:
        message = f"Refreshing devices… {event.processed:,} processed"
        self._context.set_busy(message)
        dialog = self._refresh_progress_dialog
        if dialog is not None:
            dialog.update_progress(
                ProgressUpdate(
                    total=None,
                    completed=event.processed,
                    failed=0,
                    current=message,
                ),
            )
            if event.finished:
                dialog.mark_finished()

    def _finish_refresh(self, *, mark_finished: bool = False) -> None:
        if (
            not self._refresh_in_progress
            and self._refresh_token_source is None
            and self._refresh_progress_dialog is None
        ):
            return
        dialog = self._refresh_progress_dialog
        if dialog is not None:
            if mark_finished:
                dialog.mark_finished()
            dialog.close()
            self._refresh_progress_dialog = None
        if self._refresh_token_source is not None:
            self._refresh_token_source.dispose()
            self._refresh_token_source = None
        self._refresh_in_progress = False
        self._context.clear_busy()
        self._refresh_button.setEnabled(True)
        self._force_refresh_button.setEnabled(True)

    # ----------------------------------------------------------------- Actions

    def _handle_refresh_clicked(self) -> None:
        self._start_refresh(force=False)

    def _handle_force_refresh_clicked(self) -> None:
        self._start_refresh(force=True)

    def _start_refresh(self, *, force: bool = False) -> None:
        if self._services.devices is None:
            self._list_message.display(
                "Device service unavailable. Configure Microsoft Graph dependencies in Settings.",
                level=ToastLevel.WARNING,
            )
            self._context.show_notification(
                "Device service not configured. Configure Graph dependencies in Settings.",
                level=ToastLevel.WARNING,
            )
            return
        self._list_message.clear()
        if self._refresh_token_source is not None:
            return
        token_source = CancellationTokenSource()
        dialog = ProgressDialog(
            title="Refreshing devices",
            parent=self,
            message="Preparing device refresh…",
            token_source=token_source,
        )
        dialog.show()
        self._refresh_token_source = token_source
        self._refresh_progress_dialog = dialog
        self._refresh_in_progress = True
        self._context.set_busy("Refreshing devices…")
        dialog.set_message("Refreshing devices…")
        self._refresh_button.setEnabled(False)
        self._force_refresh_button.setEnabled(False)
        self._context.run_async(
            self._refresh_async(force=force, token_source=token_source)
        )

    async def _refresh_async(
        self, *, force: bool, token_source: CancellationTokenSource
    ) -> None:
        token = token_source.token
        try:
            await self._controller.refresh(force=force, cancellation_token=token)
        except CancellationError:
            self._finish_refresh()
            self._context.show_notification(
                "Device refresh cancelled.", level=ToastLevel.INFO
            )
        except Exception:  # noqa: BLE001
            raise

    def _handle_device_action(self, action: DeviceActionName) -> None:
        if self._services.devices is None:
            return
        devices = list(self._selected_devices)
        if not devices:
            self._context.show_notification(
                "Select a device before issuing an action.",
                level=ToastLevel.WARNING,
            )
            return
        pretty = self._ACTION_LABELS.get(action, action.title())
        if len(devices) == 1:
            self._context.set_busy(f"Sending {pretty.lower()} command…")
        else:
            self._context.set_busy(
                f"Sending {pretty.lower()} command to {len(devices):,} devices…",
            )
        self._pending_actions = len(devices)
        self._bulk_action_active = len(devices) > 1
        if self._bulk_action_active:
            self._bulk_action_summary = {
                "label": pretty,
                "success": 0,
                "failure": 0,
                "total": len(devices),
            }
        else:
            self._bulk_action_summary = None
        self._update_action_buttons(disabled=True)
        self._context.run_async(self._perform_action_async(devices, action))

    async def _perform_action_async(
        self,
        devices: list[ManagedDevice],
        action: DeviceActionName,
    ) -> None:
        for device in devices:
            try:
                await self._controller.perform_action(device.id, action)
            except Exception:  # noqa: BLE001
                continue
        if self._pending_actions == 0:
            self._context.clear_busy()
            self._update_action_buttons()

    async def _load_timeline_async(
        self,
        device_id: str | None,
        *,
        aliases: Iterable[str] | None = None,
    ) -> None:
        if device_id is None:
            self._detail_pane.set_timeline(
                [],
                error="Timeline unavailable — missing device identifier.",
            )
            return
        try:
            entries = await self._controller.load_timeline(device_id, aliases=aliases)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to load device timeline", device_id=device_id)
            if self._active_timeline_device_id == device_id:
                self._detail_pane.set_timeline(
                    [],
                    error=(
                        "Timeline failed to load. Verify audit permissions and try again."
                    ),
                )
            return
        if self._active_timeline_device_id != device_id:
            return
        if not entries and self._services.audit is None:
            self._detail_pane.set_timeline(
                [],
                error="Timeline unavailable — audit service not configured.",
            )
            return
        self._detail_pane.set_timeline(entries)

    # ----------------------------------------------------------------- Filters

    def _handle_search_changed(self, text: str) -> None:
        self._proxy.set_search_text(text)
        self._update_summary()

    def _handle_platform_changed(self, index: int) -> None:  # noqa: ARG002
        platform = self._platform_combo.currentData()
        self._proxy.set_platform_filter(platform)
        self._update_summary()

    def _handle_compliance_changed(self, index: int) -> None:  # noqa: ARG002
        compliance = self._compliance_combo.currentData()
        self._proxy.set_compliance_filter(compliance)
        self._update_summary()

    def _handle_management_changed(self, index: int) -> None:  # noqa: ARG002
        management = self._management_combo.currentData()
        self._proxy.set_management_filter(management)
        self._update_summary()

    def _handle_ownership_changed(self, index: int) -> None:  # noqa: ARG002
        ownership = self._ownership_combo.currentData()
        self._proxy.set_ownership_filter(ownership)
        self._update_summary()

    def _handle_enrollment_changed(self, index: int) -> None:  # noqa: ARG002
        enrollment = self._enrollment_combo.currentData()
        self._proxy.set_enrollment_filter(enrollment)
        self._update_summary()

    def _handle_threat_changed(self, index: int) -> None:  # noqa: ARG002
        threat = self._threat_combo.currentData()
        self._proxy.set_threat_filter(threat)
        self._update_summary()

    def _apply_filter_options(self, devices: Iterable[ManagedDevice]) -> None:
        platforms = sorted(
            {
                (device.operating_system or "").strip()
                for device in devices
                if device.operating_system
            },
            key=lambda value: value.lower(),
        )
        compliance_states = sorted(
            {
                (enum_text(device.compliance_state) or "").strip()
                for device in devices
                if device.compliance_state
            },
            key=lambda value: value.lower(),
        )
        management_states = sorted(
            {
                (enum_text(device.management_state) or "").strip()
                for device in devices
                if device.management_state
            },
            key=lambda value: value.lower(),
        )
        ownership_states = sorted(
            {
                (enum_text(device.ownership) or "").strip()
                for device in devices
                if device.ownership
            },
            key=lambda value: value.lower(),
        )
        enrollment_sources = sorted(
            {
                (device.enrolled_managed_by or "").strip()
                for device in devices
                if device.enrolled_managed_by
            },
            key=lambda value: value.lower(),
        )
        threat_states = sorted(
            {
                (device.partner_reported_threat_state or "").strip()
                for device in devices
                if device.partner_reported_threat_state
            },
            key=lambda value: value.lower(),
        )
        self._populate_combo(self._platform_combo, "All platforms", platforms)
        self._populate_combo(
            self._compliance_combo, "All compliance states", compliance_states
        )
        self._populate_combo(
            self._management_combo, "All management states", management_states
        )
        self._populate_combo(self._ownership_combo, "All ownership", ownership_states)
        self._populate_combo(
            self._enrollment_combo, "All enrollment sources", enrollment_sources
        )
        self._populate_combo(self._threat_combo, "All threat states", threat_states)

    def _format_filter_label(self, value: str | None) -> str:
        if not value:
            return "Unknown"
        spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
        spaced = spaced.replace("_", " ")
        return spaced.strip().title()

    def _populate_combo(
        self, combo: QComboBox, placeholder: str, values: List[str]
    ) -> None:
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(placeholder, None)
        for value in values:
            label = self._format_filter_label(value)
            combo.addItem(label, value or None)
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
            self._selected_devices = []
            self._selected_device_ids = set()
            self._detail_pane.display_device(None)
            self._detail_pane.set_timeline(
                [], error="Select a device to view timeline."
            )
            self._active_timeline_device_id = None
            self._update_action_buttons()
            self._update_summary()
            return
        selected_devices: list[ManagedDevice] = []
        selected_ids: set[str] = set()
        for proxy_index in indexes:
            source_index = self._proxy.mapToSource(proxy_index)
            device = self._model.device_at(source_index.row())
            if device is None:
                continue
            selected_devices.append(device)
            selected_ids.add(device.id)
            self._detail_cache.put(device)
        self._selected_devices = selected_devices
        self._selected_device_ids = selected_ids
        if len(selected_devices) == 1:
            device = selected_devices[0]
            detail = self._detail_cache.get(device.id) or device
            self._detail_pane.display_device(detail)
            self._detail_pane.focus_overview()
            self._active_timeline_device_id = device.id
            self._detail_pane.set_timeline([], loading=True)
            aliases: list[str] = []
            azure_id = getattr(detail, "azure_ad_device_id", None)
            if isinstance(azure_id, str) and azure_id:
                aliases.append(azure_id)
            self._context.run_async(
                self._load_timeline_async(device.id, aliases=aliases or None)
            )
        else:
            self._detail_pane.show_placeholder(
                (
                    f"{len(selected_devices):,} devices selected. "
                    "Select a single device to inspect details or use Export to CSV for reporting."
                ),
            )
            self._detail_pane.set_timeline(
                [],
                error="Timeline available when a single device is selected.",
            )
            self._active_timeline_device_id = None
        self._update_action_buttons()
        self._update_summary()

    def _show_context_menu(self, position: QPoint) -> None:
        global_pos = self._table.viewport().mapToGlobal(position)
        index = self._table.indexAt(position)
        if index.isValid():
            selection_model = self._table.selectionModel()
            if selection_model and not selection_model.isRowSelected(
                index.row(), QModelIndex()
            ):
                selection_model.select(
                    index,
                    QItemSelectionModel.SelectionFlag.ClearAndSelect
                    | QItemSelectionModel.SelectionFlag.Rows,
                )

        menu = QMenu(self)
        has_selection = bool(self._selected_devices)
        single_selection = len(self._selected_devices) == 1
        service_available = self._services.devices is not None
        actions_enabled = (
            service_available and has_selection and not self._bulk_action_active
        )

        open_action = menu.addAction("Open details")
        open_action.setEnabled(single_selection)
        open_action.triggered.connect(self._focus_selected_detail)

        copy_name = menu.addAction("Copy device name")
        copy_name.setEnabled(single_selection)
        copy_name.triggered.connect(
            lambda: self._copy_selection_field(lambda d: d.device_name, "Device name")
        )

        copy_user = menu.addAction("Copy primary user")
        copy_user.setEnabled(single_selection)
        copy_user.triggered.connect(
            lambda: self._copy_selection_field(
                lambda d: d.user_display_name or d.user_principal_name,
                "Primary user",
            ),
        )

        copy_device_id = menu.addAction("Copy device ID")
        copy_device_id.setEnabled(single_selection)
        copy_device_id.triggered.connect(
            lambda: self._copy_selection_field(lambda d: d.id, "Device ID")
        )

        menu.addSeparator()

        export_action = menu.addAction("Export selection to CSV…")
        export_action.setEnabled(has_selection)
        export_action.triggered.connect(self._handle_export_selected)

        refresh_action = menu.addAction("Refresh devices")
        refresh_action.setEnabled(service_available and self._pending_actions == 0)
        refresh_action.triggered.connect(lambda: self._start_refresh(force=False))

        menu.addSeparator()
        for action_name, label in self._ACTION_LABELS.items():
            action = menu.addAction(label)
            action.setEnabled(actions_enabled)
            action.triggered.connect(
                lambda _, name=action_name: self._handle_device_action(name),
            )

        menu.exec(global_pos)

    def _focus_selected_detail(self) -> None:
        if not self._selected_devices:
            return
        device = self._selected_devices[0]
        detail = self._detail_cache.get(device.id) or device
        self._detail_pane.display_device(detail)
        self._detail_pane.focus_overview()

    def _copy_selection_field(
        self,
        extractor: Callable[[ManagedDevice], str | None],
        label: str,
    ) -> None:
        if not self._selected_devices:
            return
        device = self._selected_devices[0]
        value = extractor(device)
        if not value:
            self._context.show_notification(
                f"No {label.lower()} available for the selected device.",
                level=ToastLevel.INFO,
                duration_ms=4000,
            )
            return
        QGuiApplication.clipboard().setText(str(value))
        self._context.show_notification(
            f"{label} copied to clipboard.",
            level=ToastLevel.SUCCESS,
            duration_ms=2500,
        )

    def _handle_export_selected(self) -> None:
        if not self._selected_devices:
            self._context.show_notification(
                "Select at least one device to export.",
                level=ToastLevel.INFO,
                duration_ms=4000,
            )
            return

        default_dir = Path.home() / "Desktop"
        if not default_dir.exists():
            default_dir = Path.home()
        default_path = default_dir / "intune-devices.csv"

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export selected devices",
            str(default_path),
            "CSV Files (*.csv)",
        )
        if not filename:
            return

        try:
            rows = [
                self._serialize_device_for_export(device)
                for device in self._selected_devices
            ]
            if not rows:
                self._context.show_notification(
                    "No device data available to export.",
                    level=ToastLevel.WARNING,
                )
                return
            fieldnames = list(rows[0].keys())
            with open(filename, "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        except Exception as exc:  # noqa: BLE001
            self._context.show_notification(
                f"Failed to export devices: {exc}",
                level=ToastLevel.ERROR,
                duration_ms=8000,
            )
            return

        self._context.show_notification(
            f"Exported {len(rows):,} device(s) to {filename}.",
            level=ToastLevel.SUCCESS,
            duration_ms=6000,
        )

    def _handle_copy_selected_devices(self) -> None:
        devices = list(self._selected_devices)
        if not devices:
            self._context.show_notification(
                "Select at least one device before copying details.",
                level=ToastLevel.WARNING,
                duration_ms=4000,
            )
            return

        summaries: list[dict[str, object | None]] = []
        for device in devices:
            summaries.append(
                {
                    "id": device.id,
                    "deviceName": device.device_name,
                    "manufacturer": device.manufacturer,
                    "model": device.model,
                    "operatingSystem": device.operating_system,
                    "osVersion": device.os_version,
                    "primaryUser": device.user_display_name
                    or device.user_principal_name,
                    "complianceState": enum_text(device.compliance_state),
                    "managementState": enum_text(device.management_state),
                    "ownership": enum_text(device.ownership),
                    "serialNumber": device.serial_number,
                    "enrollmentType": device.enrolled_managed_by,
                    "lastSync": (
                        device.last_sync_date_time.isoformat()
                        if device.last_sync_date_time
                        else None
                    ),
                },
            )

        data: object = summaries[0] if len(summaries) == 1 else summaries
        QGuiApplication.clipboard().setText(json.dumps(data, indent=2))
        self._context.show_notification(
            f"Copied {len(summaries)} device detail{'s' if len(summaries) != 1 else ''} to clipboard.",
            level=ToastLevel.SUCCESS,
            duration_ms=3000,
        )

    def _serialize_device_for_export(self, device: ManagedDevice) -> dict[str, str]:
        return {
            "Device Name": device.device_name,
            "Primary User": device.user_display_name
            or device.user_principal_name
            or "",
            "Operating System": device.operating_system,
            "OS Version": device.os_version or "",
            "Compliance": enum_text(device.compliance_state) or "",
            "Management": enum_text(device.management_state) or "",
            "Ownership": enum_text(device.ownership) or "",
            "Enrollment": device.enrolled_managed_by or "",
            "Last Sync": DeviceDetailPane._format_datetime(device.last_sync_date_time),
            "Azure AD Device ID": device.azure_ad_device_id or "",
            "Serial Number": device.serial_number or "",
            "Wi-Fi MAC": device.wi_fi_mac_address or "",
            "Ethernet MAC": device.ethernet_mac_address or "",
            "IP Address": device.ip_address_v4 or "",
            "Manufacturer": device.manufacturer or "",
            "Model": device.model or "",
            "Threat State": device.partner_reported_threat_state or "",
        }

    def _reselect_devices(self, device_ids: set[str]) -> None:
        if not device_ids:
            return
        selection_model = self._table.selectionModel()
        if selection_model is None:
            return
        selection_model.clearSelection()
        for row in range(self._model.rowCount()):
            device = self._model.device_at(row)
            if device is None or device.id not in device_ids:
                continue
            proxy_index = self._proxy.mapFromSource(self._model.index(row, 0))
            if proxy_index.isValid():
                selection_model.select(
                    proxy_index,
                    QItemSelectionModel.SelectionFlag.Select
                    | QItemSelectionModel.SelectionFlag.Rows,
                )
                self._table.scrollTo(proxy_index)

    # ----------------------------------------------------------------- Helpers

    def _update_summary(self) -> None:
        visible = self._proxy.rowCount()
        total_cached = self._total_devices
        stale = self._services.devices is not None and self._controller.is_cache_stale()

        parts = [f"{visible:,} devices shown"]
        if self._model.is_loading():
            parts[-1] += " (loading…)"

        if total_cached and total_cached != visible:
            parts.append(f"{total_cached:,} cached")
        elif total_cached and not self._model.is_loading():
            parts.append(f"{total_cached:,} cached")

        if stale:
            parts.append("Cache stale — refresh recommended")
        if self._selected_devices:
            parts.append(f"{len(self._selected_devices):,} selected")
        if self._bulk_action_active and self._bulk_action_summary is not None:
            remaining = self._bulk_action_summary["total"] - (
                self._bulk_action_summary["success"]
                + self._bulk_action_summary["failure"]
            )
            if remaining > 0:
                parts.append(f"Bulk action in progress ({remaining} remaining)")
        if self._last_refresh:
            parts.append(f"Updated {format_relative_timestamp(self._last_refresh)}")
            self._summary_label.setToolTip(
                f"Last refresh: {self._last_refresh.strftime('%Y-%m-%d %H:%M:%S')} UTC"
            )
        else:
            parts.append("Never refreshed")
            self._summary_label.setToolTip("No refresh recorded yet.")
        self._summary_label.setText(" · ".join(parts))

    def _update_action_buttons(self, disabled: bool | None = None) -> None:
        service_available = self._services.devices is not None
        has_selection = bool(self._selected_devices)
        enable_actions = (
            service_available and has_selection and self._pending_actions == 0
        )
        if disabled is not None and disabled:
            enable_actions = False
        if self._pending_actions > 0:
            enable_actions = False
        for button in [
            self._sync_device_button,
            self._retire_button,
            self._wipe_button,
            self._reboot_button,
            self._shutdown_button,
        ]:
            button.setEnabled(enable_actions)

        refresh_enabled = service_available and self._pending_actions == 0
        self._refresh_button.setEnabled(refresh_enabled)
        self._force_refresh_button.setEnabled(refresh_enabled)
        self._export_button.setEnabled(bool(self._selected_devices))
        self._copy_button.setEnabled(bool(self._selected_devices))

    def _handle_service_unavailable(self) -> None:
        self._table.setEnabled(False)
        self._detail_pane.show_placeholder(
            "Device service not configured. Configure Microsoft Graph credentials in Settings.",
        )
        self._list_message.display(
            "Device service unavailable. Configure Microsoft Graph dependencies to load devices.",
            level=ToastLevel.WARNING,
        )
        self._context.show_banner(
            "Device service unavailable — configure data services before managing devices.",
            level=ToastLevel.WARNING,
        )
        self._update_action_buttons()

    def _cleanup(self) -> None:
        self._finish_refresh()
        if self._command_unregister:
            try:
                self._command_unregister()
            except Exception:  # pragma: no cover - defensive unregister
                pass
            self._command_unregister = None
        self._controller.dispose()


__all__ = ["DevicesWidget"]
