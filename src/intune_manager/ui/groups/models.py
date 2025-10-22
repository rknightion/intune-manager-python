from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, List, Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QSortFilterProxyModel

from intune_manager.data import DirectoryGroup


def _group_type_label(group: DirectoryGroup) -> str:
    types = group.group_types or []
    if "Unified" in types:
        return "Microsoft 365"
    if "DynamicMembership" in types:
        return "Dynamic"
    if "Security" in types:
        return "Security"
    return "Unknown"


@dataclass(slots=True)
class GroupColumn:
    key: str
    header: str
    accessor: Callable[[DirectoryGroup], str | bool | None]


class GroupTableModel(QAbstractTableModel):
    """Table projection for directory groups."""

    def __init__(self, groups: Sequence[DirectoryGroup] | None = None) -> None:
        super().__init__()
        self._columns: List[GroupColumn] = [
            GroupColumn("display_name", "Group", lambda group: group.display_name),
            GroupColumn("description", "Description", lambda group: group.description),
            GroupColumn("type", "Type", _group_type_label),
            GroupColumn("mail", "Mail", lambda group: group.mail or group.mail_nickname),
            GroupColumn("security_enabled", "Security", lambda group: "Yes" if group.security_enabled else "No"),
        ]
        self._groups: list[DirectoryGroup] = list(groups or [])

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        if parent and parent.isValid():
            return 0
        return len(self._groups)

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        if parent and parent.isValid():
            return 0
        return len(self._columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802, ANN001
        if not index.isValid():
            return None

        row = index.row()
        column = index.column()
        if row < 0 or row >= len(self._groups):
            return None

        group = self._groups[row]
        column_meta = self._columns[column]

        if role == Qt.ItemDataRole.DisplayRole:
            value = column_meta.accessor(group)
            display = value if value not in {None, ""} else "—"
            if column_meta.key == "display_name":
                badge = _group_type_label(group)
                display = f"{display} [{badge}]"
            return display

        if role == Qt.ItemDataRole.UserRole:
            return group

        return None

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if orientation != Qt.Orientation.Horizontal:
            return super().headerData(section, orientation, role)
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if section < 0 or section >= len(self._columns):
            return None
        return self._columns[section].header

    def set_groups(self, groups: Iterable[DirectoryGroup]) -> None:
        self.beginResetModel()
        self._groups = list(groups)
        self.endResetModel()

    def group_at(self, row: int) -> DirectoryGroup | None:
        if 0 <= row < len(self._groups):
            return self._groups[row]
        return None

    def groups(self) -> list[DirectoryGroup]:
        return list(self._groups)


class GroupFilterProxyModel(QSortFilterProxyModel):
    """Proxy model providing search/type filters for groups."""

    def __init__(self) -> None:
        super().__init__()
        self._search_text: str = ""
        self._type_filter: str | None = None
        self._mail_state: str | None = None
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def set_search_text(self, text: str) -> None:
        normalised = text.strip().lower()
        if self._search_text == normalised:
            return
        self._search_text = normalised
        self.invalidateFilter()

    def set_type_filter(self, group_type: str | None) -> None:
        key = group_type.lower() if group_type else None
        if self._type_filter == key:
            return
        self._type_filter = key
        self.invalidateFilter()

    def set_mail_filter(self, state: str | None) -> None:
        key = state.lower() if state else None
        if self._mail_state == key:
            return
        self._mail_state = key
        self.invalidateFilter()

    def filterAcceptsRow(  # noqa: N802
        self,
        source_row: int,
        source_parent: QModelIndex,
    ) -> bool:
        model = self.sourceModel()
        if not isinstance(model, GroupTableModel):
            return True
        group = model.group_at(source_row)
        if group is None:
            return True

        if self._search_text:
            haystack = [
                group.display_name,
                group.description,
                group.mail,
                group.mail_nickname,
            ]
            if not any(
                self._search_text in value.lower()
                for value in haystack
                if isinstance(value, str)
            ):
                return False

        if self._type_filter:
            type_label = _group_type_label(group).lower()
            if type_label != self._type_filter:
                return False

        if self._mail_state:
            mail_enabled = bool(group.mail_enabled)
            if self._mail_state == "enabled" and not mail_enabled:
                return False
            if self._mail_state == "disabled" and mail_enabled:
                return False

        return True


__all__ = ["GroupTableModel", "GroupFilterProxyModel", "_group_type_label"]
