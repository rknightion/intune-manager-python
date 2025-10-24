from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable, List, Sequence, TYPE_CHECKING

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    Qt,
    QSortFilterProxyModel,
    QTimer,
    Signal,
)

from intune_manager.data import ManagedDevice

if TYPE_CHECKING:
    from intune_manager.data import AuditEvent


@dataclass(slots=True)
class DeviceTimelineEntry:
    """Timeline metadata rendered in the device detail pane."""

    timestamp: datetime | None
    title: str
    description: str | None = None
    actor: str | None = None
    category: str | None = None
    result: str | None = None
    source: str = "audit"

    @classmethod
    def from_audit_event(cls, event: "AuditEvent") -> "DeviceTimelineEntry":
        actor = None
        if getattr(event, "actor", None):
            actor = (
                event.actor.user_principal_name
                or event.actor.application_display_name
                or event.actor.service_principal_name
                or event.actor.ip_address
            )
        description_parts = []
        if getattr(event, "activity_type", None):
            description_parts.append(event.activity_type)
        if getattr(event, "activity_operation_type", None) and (
            event.activity_operation_type != event.activity_type
        ):
            description_parts.append(event.activity_operation_type)
        if getattr(event, "component_name", None):
            description_parts.append(event.component_name)
        description = " • ".join(part for part in description_parts if part)
        title = event.activity or event.display_name or "Device activity"
        if description and description == title:
            description = None
        return cls(
            timestamp=event.activity_date_time,
            title=title,
            description=description or event.display_name,
            actor=actor,
            category=event.category or event.component_name,
            result=event.activity_result,
            source="audit",
        )

    @staticmethod
    def references_device(event: "AuditEvent", device_id: str | None) -> bool:
        if not device_id or not getattr(event, "resources", None):
            return False
        target = device_id.lower()
        for resource in event.resources or []:
            resource_id = (resource.resource_id or "").lower()
            if resource_id == target:
                return True
            if resource_id.endswith(target):
                return True
            display = (resource.display_name or "").lower()
            if display and display == target:
                return True
        return False

    def formatted_timestamp(self) -> str:
        if self.timestamp is None:
            return "Unknown time"
        return self.timestamp.strftime("%Y-%m-%d %H:%M")

@dataclass(slots=True)
class DeviceColumn:
    key: str
    header: str
    accessor: Callable[[ManagedDevice], str | int | float | None]
    alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%Y-%m-%d %H:%M")


class DeviceTableModel(QAbstractTableModel):
    """Table model projecting managed devices for the grid view."""

    load_finished = Signal()
    batch_appended = Signal(int)

    def __init__(self, devices: Sequence[ManagedDevice] | None = None) -> None:
        super().__init__()
        self._columns: List[DeviceColumn] = [
            DeviceColumn(
                "device_name",
                "Device",
                lambda device: device.device_name,
            ),
            DeviceColumn(
                "user",
                "Primary User",
                lambda device: device.user_display_name or device.user_principal_name,
            ),
            DeviceColumn(
                "operating_system",
                "OS",
                lambda device: device.operating_system,
            ),
            DeviceColumn(
                "os_version",
                "OS Version",
                lambda device: device.os_version,
            ),
            DeviceColumn(
                "compliance_state",
                "Compliance",
                lambda device: (
                    device.compliance_state.value if device.compliance_state else None
                ),
            ),
            DeviceColumn(
                "management_state",
                "Management",
                lambda device: (
                    device.management_state.value if device.management_state else None
                ),
            ),
            DeviceColumn(
                "ownership",
                "Ownership",
                lambda device: (device.ownership.value if device.ownership else None),
            ),
            DeviceColumn(
                "enrolled_managed_by",
                "Enrollment",
                lambda device: device.enrolled_managed_by,
            ),
            DeviceColumn(
                "last_sync_date_time",
                "Last Sync",
                lambda device: _format_datetime(device.last_sync_date_time),
            ),
        ]
        self._devices: list[ManagedDevice] = list(devices or [])
        self._pending_devices: deque[ManagedDevice] = deque()
        self._insert_timer: QTimer | None = None
        self._chunk_size = 500

    # ----------------------------------------------------------------- Qt API

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        if parent and parent.isValid():
            return 0
        return len(self._devices)

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        if parent and parent.isValid():
            return 0
        return len(self._columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802, ANN001
        if not index.isValid():
            return None

        row = index.row()
        column = index.column()
        if row < 0 or row >= len(self._devices):
            return None

        device = self._devices[row]
        column_meta = self._columns[column]

        if role == Qt.ItemDataRole.DisplayRole:
            value = column_meta.accessor(device)
            if value is None:
                return "—"
            if isinstance(value, float):
                return f"{value:.2f}"
            return str(value)

        if role == Qt.ItemDataRole.UserRole:
            return device

        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(column_meta.alignment)

        return None

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if orientation != Qt.Orientation.Horizontal:
            return super().headerData(section, orientation, role)
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if section < 0 or section >= len(self._columns):
            return None
        return self._columns[section].header

    # ----------------------------------------------------------------- Helpers

    def set_devices(self, devices: Iterable[ManagedDevice]) -> None:
        if self._insert_timer and self._insert_timer.isActive():
            self._insert_timer.stop()
        self._pending_devices.clear()
        self.beginResetModel()
        self._devices = list(devices)
        self.endResetModel()
        self.load_finished.emit()

    def set_devices_lazy(
        self,
        devices: Iterable[ManagedDevice],
        *,
        chunk_size: int = 500,
    ) -> None:
        if self._insert_timer and self._insert_timer.isActive():
            self._insert_timer.stop()
        self.beginResetModel()
        self._devices = []
        self.endResetModel()
        self._pending_devices = deque(devices)
        self._chunk_size = max(1, chunk_size)
        if self._insert_timer is None:
            self._insert_timer = QTimer(self)
            self._insert_timer.setTimerType(Qt.TimerType.PreciseTimer)
            self._insert_timer.timeout.connect(self._consume_pending_devices)
        if not self._pending_devices:
            self.load_finished.emit()
            return
        self._insert_timer.start(0)

    def device_at(self, row: int) -> ManagedDevice | None:
        if 0 <= row < len(self._devices):
            return self._devices[row]
        return None

    def devices(self) -> list[ManagedDevice]:
        return list(self._devices)

    def is_loading(self) -> bool:
        return bool(self._pending_devices)

    def column_index(self, key: str) -> int | None:
        for index, column in enumerate(self._columns):
            if column.key == key:
                return index
        return None

    # ------------------------------------------------------------- Lazy insert

    def _consume_pending_devices(self) -> None:
        if not self._pending_devices:
            if self._insert_timer and self._insert_timer.isActive():
                self._insert_timer.stop()
            self.load_finished.emit()
            return

        batch: list[ManagedDevice] = []
        while self._pending_devices and len(batch) < self._chunk_size:
            batch.append(self._pending_devices.popleft())

        if not batch:
            return

        start = len(self._devices)
        end = start + len(batch) - 1
        self.beginInsertRows(QModelIndex(), start, end)
        self._devices.extend(batch)
        self.endInsertRows()
        self.batch_appended.emit(len(batch))

        if (
            not self._pending_devices
            and self._insert_timer
            and self._insert_timer.isActive()
        ):
            self._insert_timer.stop()
            self.load_finished.emit()


class DeviceFilterProxyModel(QSortFilterProxyModel):
    """Search and filter helper for the device grid."""

    def __init__(self) -> None:
        super().__init__()
        self._search_text: str = ""
        self._platform_filter: str | None = None
        self._compliance_filter: str | None = None
        self._management_filter: str | None = None
        self._ownership_filter: str | None = None
        self._enrollment_filter: str | None = None
        self._threat_filter: str | None = None
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setDynamicSortFilter(True)

    # ------------------------------------------------------------- Properties

    def set_search_text(self, text: str) -> None:
        normalised = text.strip().lower()
        if self._search_text == normalised:
            return
        self._search_text = normalised
        self.invalidateFilter()

    def set_platform_filter(self, platform: str | None) -> None:
        key = platform.lower() if platform else None
        if self._platform_filter == key:
            return
        self._platform_filter = key
        self.invalidateFilter()

    def set_compliance_filter(self, compliance: str | None) -> None:
        key = compliance.lower() if compliance else None
        if self._compliance_filter == key:
            return
        self._compliance_filter = key
        self.invalidateFilter()

    def set_management_filter(self, state: str | None) -> None:
        key = state.lower() if state else None
        if self._management_filter == key:
            return
        self._management_filter = key
        self.invalidateFilter()

    def set_ownership_filter(self, ownership: str | None) -> None:
        key = ownership.lower() if ownership else None
        if self._ownership_filter == key:
            return
        self._ownership_filter = key
        self.invalidateFilter()

    def set_enrollment_filter(self, enrollment: str | None) -> None:
        key = enrollment.lower() if enrollment else None
        if self._enrollment_filter == key:
            return
        self._enrollment_filter = key
        self.invalidateFilter()

    def set_threat_filter(self, threat: str | None) -> None:
        key = threat.lower() if threat else None
        if self._threat_filter == key:
            return
        self._threat_filter = key
        self.invalidateFilter()

    # --------------------------------------------------------------- Filtering

    def filterAcceptsRow(  # noqa: N802
        self,
        source_row: int,
        source_parent: QModelIndex,
    ) -> bool:
        model = self.sourceModel()
        if not isinstance(model, DeviceTableModel):
            return True
        device = model.device_at(source_row)
        if device is None:
            return True

        if self._search_text:
            haystack = [
                device.device_name,
                device.user_display_name,
                device.user_principal_name,
                device.serial_number,
                device.azure_ad_device_id,
                device.manufacturer,
                device.model,
                device.enrolled_managed_by,
                device.device_registration_state,
                device.device_category_display_name,
                device.operating_system,
            ]
            if not any(
                self._search_text in value.lower()
                for value in haystack
                if isinstance(value, str)
            ):
                return False

        if self._platform_filter:
            os_name = (device.operating_system or "").lower()
            if not os_name.startswith(self._platform_filter):
                return False

        if self._compliance_filter:
            compliance = (
                device.compliance_state.value.lower() if device.compliance_state else ""
            )
            if compliance != self._compliance_filter:
                return False

        if self._management_filter:
            management = (
                device.management_state.value.lower() if device.management_state else ""
            )
            if management != self._management_filter:
                return False

        if self._ownership_filter:
            ownership = (
                device.ownership.value.lower() if device.ownership else ""
            )
            if ownership != self._ownership_filter:
                return False

        if self._enrollment_filter:
            enrollment = (device.enrolled_managed_by or "").lower()
            if enrollment != self._enrollment_filter:
                return False

        if self._threat_filter:
            threat = (device.partner_reported_threat_state or "").lower()
            if threat != self._threat_filter:
                return False

        return True


__all__ = ["DeviceTimelineEntry", "DeviceTableModel", "DeviceFilterProxyModel"]
