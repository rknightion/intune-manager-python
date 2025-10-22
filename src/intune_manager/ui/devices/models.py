from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable, List, Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QSortFilterProxyModel

from intune_manager.data import ManagedDevice


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
                lambda device: (device.compliance_state.value if device.compliance_state else None),
            ),
            DeviceColumn(
                "management_state",
                "Management",
                lambda device: (device.management_state.value if device.management_state else None),
            ),
            DeviceColumn(
                "ownership",
                "Ownership",
                lambda device: (device.ownership.value if device.ownership else None),
            ),
            DeviceColumn(
                "last_sync_date_time",
                "Last Sync",
                lambda device: _format_datetime(device.last_sync_date_time),
            ),
        ]
        self._devices: list[ManagedDevice] = list(devices or [])

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
        self.beginResetModel()
        self._devices = list(devices)
        self.endResetModel()

    def device_at(self, row: int) -> ManagedDevice | None:
        if 0 <= row < len(self._devices):
            return self._devices[row]
        return None

    def devices(self) -> list[ManagedDevice]:
        return list(self._devices)


class DeviceFilterProxyModel(QSortFilterProxyModel):
    """Search and filter helper for the device grid."""

    def __init__(self) -> None:
        super().__init__()
        self._search_text: str = ""
        self._platform_filter: str | None = None
        self._compliance_filter: str | None = None
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

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
                device.compliance_state.value.lower()
                if device.compliance_state
                else ""
            )
            if compliance != self._compliance_filter:
                return False

        return True


__all__ = ["DeviceTableModel", "DeviceFilterProxyModel"]
