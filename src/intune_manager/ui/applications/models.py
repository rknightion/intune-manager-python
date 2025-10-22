from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable, List, Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QSortFilterProxyModel
from PySide6.QtGui import QIcon

from intune_manager.data import MobileApp


@dataclass(slots=True)
class ApplicationColumn:
    key: str
    header: str
    accessor: Callable[[MobileApp], str | int | None]


def _format_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%Y-%m-%d %H:%M")


def assignment_summary(app: MobileApp) -> str:
    assignments = app.assignments or []
    if not assignments:
        return "No assignments"
    counter: Counter[str] = Counter()
    for assignment in assignments:
        counter[assignment.intent.value] += 1
    parts = [f"{intent}: {count}" for intent, count in counter.items()]
    return ", ".join(parts)


class ApplicationTableModel(QAbstractTableModel):
    """Table projection for managed mobile applications."""

    def __init__(
        self,
        apps: Sequence[MobileApp] | None = None,
        *,
        icon_provider: Callable[[str], QIcon | None] | None = None,
    ) -> None:
        super().__init__()
        self._columns: List[ApplicationColumn] = [
            ApplicationColumn("display_name", "Application", lambda app: app.display_name),
            ApplicationColumn(
                "platform_type",
                "Platform",
                lambda app: app.platform_type.value if app.platform_type else None,
            ),
            ApplicationColumn("publisher", "Publisher", lambda app: app.publisher),
            ApplicationColumn("owner", "Owner", lambda app: app.owner),
            ApplicationColumn(
                "last_modified",
                "Last modified",
                lambda app: _format_timestamp(app.last_modified_date_time),
            ),
            ApplicationColumn("assignments", "Assignments", assignment_summary),
        ]
        self._apps: list[MobileApp] = list(apps or [])
        self._icon_provider = icon_provider or (lambda _: None)

    # ----------------------------------------------------------------- Qt API

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        if parent and parent.isValid():
            return 0
        return len(self._apps)

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        if parent and parent.isValid():
            return 0
        return len(self._columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802, ANN001
        if not index.isValid():
            return None

        row = index.row()
        column = index.column()
        if row < 0 or row >= len(self._apps):
            return None

        app = self._apps[row]
        column_meta = self._columns[column]

        if role == Qt.ItemDataRole.DisplayRole:
            value = column_meta.accessor(app)
            return value or "—"

        if role == Qt.ItemDataRole.DecorationRole and column == 0:
            icon = self._icon_provider(app.id)
            return icon

        if role == Qt.ItemDataRole.ToolTipRole and column == 0:
            return app.description or ""

        if role == Qt.ItemDataRole.UserRole:
            return app

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

    # ----------------------------------------------------------------- Helpers

    def set_apps(self, apps: Iterable[MobileApp]) -> None:
        self.beginResetModel()
        self._apps = list(apps)
        self.endResetModel()

    def app_at(self, row: int) -> MobileApp | None:
        if 0 <= row < len(self._apps):
            return self._apps[row]
        return None

    def apps(self) -> list[MobileApp]:
        return list(self._apps)

    def set_icon_provider(self, provider: Callable[[str], QIcon | None]) -> None:
        self._icon_provider = provider


class ApplicationFilterProxyModel(QSortFilterProxyModel):
    """Proxy model supporting search and platform/intent filtering."""

    def __init__(self) -> None:
        super().__init__()
        self._search_text: str = ""
        self._platform_filter: str | None = None
        self._intent_filter: str | None = None
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

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

    def set_intent_filter(self, intent: str | None) -> None:
        key = intent.lower() if intent else None
        if self._intent_filter == key:
            return
        self._intent_filter = key
        self.invalidateFilter()

    def filterAcceptsRow(  # noqa: N802
        self,
        source_row: int,
        source_parent: QModelIndex,
    ) -> bool:
        model = self.sourceModel()
        if not isinstance(model, ApplicationTableModel):
            return True
        app = model.app_at(source_row)
        if app is None:
            return True

        if self._search_text:
            haystack = [
                app.display_name,
                app.description,
                app.publisher,
                app.owner,
            ]
            if not any(
                self._search_text in value.lower()
                for value in haystack
                if isinstance(value, str)
            ):
                return False

        if self._platform_filter:
            platform = (app.platform_type.value if app.platform_type else "").lower()
            if platform != self._platform_filter:
                return False

        if self._intent_filter:
            assignments = app.assignments or []
            if not any(
                assignment.intent.value.lower() == self._intent_filter
                for assignment in assignments
            ):
                return False

        return True


__all__ = ["ApplicationTableModel", "ApplicationFilterProxyModel", "assignment_summary"]
