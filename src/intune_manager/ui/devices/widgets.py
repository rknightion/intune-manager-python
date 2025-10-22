from __future__ import annotations

from collections.abc import Callable
from typing import Iterable, List

from PySide6.QtCore import Qt, QItemSelectionModel
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from intune_manager.data import ManagedDevice
from intune_manager.graph.requests import DeviceActionName
from intune_manager.services import ServiceErrorEvent, ServiceRegistry
from intune_manager.services.devices import DeviceActionEvent, DeviceRefreshProgressEvent
from intune_manager.ui.components import (
    CommandAction,
    PageScaffold,
    ToastLevel,
    UIContext,
    make_toolbar_button,
)

from .controller import DeviceController
from .models import DeviceFilterProxyModel, DeviceTableModel


def _format_value(value: object | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


class DeviceDetailPane(QWidget):
    """Right-hand pane displaying selected device information."""

    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._stack = QStackedLayout(self)

        self._empty_state = QWidget()
        empty_layout = QVBoxLayout(self._empty_state)
        empty_layout.setContentsMargins(24, 24, 24, 24)
        empty_layout.addStretch()
        self._empty_label = QLabel(
            "Select a device to inspect compliance, ownership, and installed applications.",
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

        self._form_container = QWidget()
        self._form_layout = QFormLayout(self._form_container)
        self._form_layout.setContentsMargins(0, 0, 0, 0)
        self._form_layout.setSpacing(6)
        detail_layout.addWidget(self._form_container)

        self._form_fields: dict[str, QLabel] = {}
        for key, label in [
            ("user", "Primary user"),
            ("ownership", "Ownership"),
            ("compliance", "Compliance"),
            ("management", "Management"),
            ("platform", "Platform"),
            ("last_sync", "Last sync"),
            ("serial", "Serial"),
            ("azure_id", "Azure AD device ID"),
            ("enrollment", "Enrollment"),
        ]:
            value_label = QLabel("—")
            value_label.setWordWrap(True)
            self._form_fields[key] = value_label
            self._form_layout.addRow(f"{label}:", value_label)

        self._apps_label = QLabel("Installed applications")
        self._apps_label.setProperty("class", "section-heading")
        detail_layout.addWidget(self._apps_label)

        self._apps_list = QListWidget()
        self._apps_list.setObjectName("InstalledAppsList")
        self._apps_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        detail_layout.addWidget(self._apps_list, stretch=1)

        self._stack.addWidget(self._detail_widget)

    def show_placeholder(self, message: str) -> None:
        self._empty_label.setText(message)
        self._stack.setCurrentWidget(self._empty_state)

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

        self._set_field("user", _format_value(device.user_display_name or device.user_principal_name))
        self._set_field(
            "ownership",
            _format_value(device.ownership.value if device.ownership else None),
        )
        self._set_field(
            "compliance",
            _format_value(device.compliance_state.value if device.compliance_state else None),
        )
        self._set_field(
            "management",
            _format_value(device.management_state.value if device.management_state else None),
        )
        self._set_field(
            "platform",
            f"{device.operating_system} {device.os_version or ''}".strip(),
        )
        self._set_field(
            "last_sync",
            _format_value(device.last_sync_date_time.strftime("%Y-%m-%d %H:%M") if device.last_sync_date_time else None),
        )
        self._set_field("serial", _format_value(device.serial_number))
        self._set_field("azure_id", _format_value(device.azure_ad_device_id))
        self._set_field(
            "enrollment",
            _format_value(device.enrolled_managed_by),
        )

        self._apps_list.clear()
        apps = device.installed_apps or []
        if not apps:
            placeholder = QListWidgetItem("Installed application inventory not loaded.")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._apps_list.addItem(placeholder)
            return

        for app in sorted(apps, key=lambda item: (item.display_name or "").lower()):
            name = app.display_name or "Unknown application"
            version = app.version or "—"
            publisher = app.publisher or ""
            text = f"{name} ({version})"
            if publisher:
                text += f" — {publisher}"
            item = QListWidgetItem(text)
            item.setToolTip(
                f"Install state: {app.install_state or 'unknown'}\n"
                f"Last sync: {app.last_sync_date_time or 'n/a'}",
            )
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._apps_list.addItem(item)

    def _set_field(self, key: str, value: str) -> None:
        label = self._form_fields.get(key)
        if label:
            label.setText(value)


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

        actions: List[QToolButton] = [
            self._refresh_button,
            self._force_refresh_button,
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

        self._selected_devices: list[ManagedDevice] = []
        self._selected_device_ids: set[str] = set()
        self._pending_actions = 0
        self._bulk_action_active = False
        self._bulk_action_summary: dict[str, int | str] | None = None
        self._command_unregister: Callable[[], None] | None = None

        self._build_filters()
        self._build_body()

        self._refresh_button.clicked.connect(self._handle_refresh_clicked)
        self._force_refresh_button.clicked.connect(self._handle_force_refresh_clicked)
        self._sync_device_button.clicked.connect(lambda: self._handle_device_action("syncDevice"))
        self._retire_button.clicked.connect(lambda: self._handle_device_action("retire"))
        self._wipe_button.clicked.connect(lambda: self._handle_device_action("wipe"))
        self._reboot_button.clicked.connect(lambda: self._handle_device_action("rebootNow"))
        self._shutdown_button.clicked.connect(lambda: self._handle_device_action("shutDown"))

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
        self._compliance_combo.currentIndexChanged.connect(self._handle_compliance_changed)
        layout.addWidget(self._compliance_combo)

        self._summary_label = QLabel()
        self._summary_label.setObjectName("DeviceSummaryLabel")
        self._summary_label.setStyleSheet("color: palette(mid);")
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

        self._table = QTableView()
        self._table.setObjectName("DeviceTable")
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

    # ----------------------------------------------------------------- Data flow

    def _load_cached_devices(self) -> None:
        devices = self._controller.list_cached()
        self._model.set_devices(devices)
        self._apply_filter_options(devices)
        self._update_summary()
        if devices:
            self._table.selectRow(0)

    def _handle_devices_refreshed(
        self,
        devices: Iterable[ManagedDevice],
        from_cache: bool,
    ) -> None:
        devices_list = list(devices)
        previous_ids = set(self._selected_device_ids)
        self._model.set_devices(devices_list)
        self._apply_filter_options(devices_list)
        self._update_summary()
        if previous_ids:
            self._reselect_devices(previous_ids)
        elif devices_list:
            self._table.selectRow(0)
        if not from_cache:
            self._context.show_notification(
                f"Loaded {len(devices_list):,} devices from Microsoft Graph.",
                level=ToastLevel.SUCCESS,
            )
        self._context.clear_busy()
        self._refresh_button.setEnabled(True)
        self._force_refresh_button.setEnabled(True)

    def _handle_service_error(self, event: ServiceErrorEvent) -> None:
        self._context.clear_busy()
        self._refresh_button.setEnabled(True)
        self._force_refresh_button.setEnabled(True)
        detail = str(event.error)
        self._context.show_notification(
            f"Device operation failed: {detail}",
            level=ToastLevel.ERROR,
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
            processed = self._bulk_action_summary["success"] + self._bulk_action_summary["failure"]
            total = self._bulk_action_summary["total"]
            remaining = max(total - processed, 0)
            self._context.set_busy_message(
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
                message = (
                    f"{summary['label']} completed for {total} device(s): {successes} success, {failures} failed."
                )
                self._context.show_notification(message, level=level, duration_ms=6000)
            self._bulk_action_active = False
            self._bulk_action_summary = None
            self._context.clear_busy()
            self._update_action_buttons()

    def _handle_refresh_progress(self, event: DeviceRefreshProgressEvent) -> None:
        self._context.set_busy_message(
            f"Refreshing devices… {event.processed:,} processed",
        )

    # ----------------------------------------------------------------- Actions

    def _handle_refresh_clicked(self) -> None:
        self._start_refresh(force=False)

    def _handle_force_refresh_clicked(self) -> None:
        self._start_refresh(force=True)

    def _start_refresh(self, *, force: bool = False) -> None:
        if self._services.devices is None:
            self._context.show_notification(
                "Device service not configured. Configure Graph dependencies in Settings.",
                level=ToastLevel.WARNING,
            )
            return
        self._context.set_busy("Refreshing devices…")
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
                f"Failed to refresh devices: {exc}",
                level=ToastLevel.ERROR,
            )

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
                (device.compliance_state.value if device.compliance_state else "").strip()
                for device in devices
                if device.compliance_state
            },
            key=lambda value: value.lower(),
        )
        self._populate_combo(self._platform_combo, "All platforms", platforms)
        self._populate_combo(self._compliance_combo, "All compliance states", compliance_states)

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
            self._selected_devices = []
            self._selected_device_ids = set()
            self._detail_pane.display_device(None)
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
        self._selected_devices = selected_devices
        self._selected_device_ids = selected_ids
        if len(selected_devices) == 1:
            self._detail_pane.display_device(selected_devices[0])
        else:
            self._detail_pane.show_placeholder(
                f"{len(selected_devices):,} devices selected. Select a single device to inspect details.",
            )
        self._update_action_buttons()
        self._update_summary()

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
                    QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
                )
                self._table.scrollTo(proxy_index)

    # ----------------------------------------------------------------- Helpers

    def _update_summary(self) -> None:
        total = self._model.rowCount()
        visible = self._proxy.rowCount()
        stale = False
        if self._services.devices is not None:
            stale = self._controller.is_cache_stale()
        parts = [f"{visible:,} devices shown"]
        if visible != total:
            parts.append(f"{total:,} cached")
        if stale:
            parts.append("Cache stale — refresh recommended")
        if self._selected_devices:
            parts.append(f"{len(self._selected_devices):,} selected")
        self._summary_label.setText(" · ".join(parts))

    def _update_action_buttons(self, disabled: bool | None = None) -> None:
        service_available = self._services.devices is not None
        has_selection = bool(self._selected_devices)
        enable_actions = service_available and has_selection and self._pending_actions == 0
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

    def _handle_service_unavailable(self) -> None:
        self._table.setEnabled(False)
        self._detail_pane.show_placeholder(
            "Device service not configured. Configure Microsoft Graph credentials in Settings.",
        )
        self._context.show_banner(
            "Device service unavailable — configure data services before managing devices.",
            level=ToastLevel.WARNING,
        )
        self._update_action_buttons()

    def _cleanup(self) -> None:
        if self._command_unregister:
            try:
                self._command_unregister()
            except Exception:  # pragma: no cover - defensive unregister
                pass
            self._command_unregister = None
        self._controller.dispose()


__all__ = ["DevicesWidget"]
