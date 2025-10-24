from __future__ import annotations

from collections import Counter, deque
from difflib import SequenceMatcher
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable, List, Sequence

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    Qt,
    QSortFilterProxyModel,
    QTimer,
    Signal,
)
from PySide6.QtGui import QIcon

from intune_manager.data import MobileApp
from intune_manager.utils.sanitize import sanitize_search_text


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

    load_finished = Signal()
    batch_appended = Signal(int)

    def __init__(
        self,
        apps: Sequence[MobileApp] | None = None,
        *,
        icon_provider: Callable[[str], QIcon | None] | None = None,
    ) -> None:
        super().__init__()
        self._columns: List[ApplicationColumn] = [
            ApplicationColumn(
                "display_name", "Application", lambda app: app.display_name
            ),
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
        self._pending_apps: deque[MobileApp] = deque()
        self._insert_timer: QTimer | None = None
        self._chunk_size = 400

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
        if self._insert_timer and self._insert_timer.isActive():
            self._insert_timer.stop()
        self._pending_apps.clear()
        self.beginResetModel()
        self._apps = list(apps)
        self.endResetModel()
        self.load_finished.emit()

    def set_apps_lazy(
        self, apps: Iterable[MobileApp], *, chunk_size: int = 400
    ) -> None:
        if self._insert_timer and self._insert_timer.isActive():
            self._insert_timer.stop()
        self.beginResetModel()
        self._apps = []
        self.endResetModel()
        self._pending_apps = deque(apps)
        self._chunk_size = max(1, chunk_size)
        if self._insert_timer is None:
            self._insert_timer = QTimer(self)
            self._insert_timer.setTimerType(Qt.TimerType.PreciseTimer)
            self._insert_timer.timeout.connect(self._consume_pending_apps)
        if not self._pending_apps:
            self.load_finished.emit()
            return
        self._insert_timer.start(0)

    def app_at(self, row: int) -> MobileApp | None:
        if 0 <= row < len(self._apps):
            return self._apps[row]
        return None

    def apps(self) -> list[MobileApp]:
        return list(self._apps)

    def set_icon_provider(self, provider: Callable[[str], QIcon | None]) -> None:
        self._icon_provider = provider

    def is_loading(self) -> bool:
        return bool(self._pending_apps)

    def _consume_pending_apps(self) -> None:
        if not self._pending_apps:
            if self._insert_timer and self._insert_timer.isActive():
                self._insert_timer.stop()
            self.load_finished.emit()
            return
        chunk: list[MobileApp] = []
        while self._pending_apps and len(chunk) < self._chunk_size:
            chunk.append(self._pending_apps.popleft())
        if not chunk:
            return
        start = len(self._apps)
        end = start + len(chunk) - 1
        self.beginInsertRows(QModelIndex(), start, end)
        self._apps.extend(chunk)
        self.endInsertRows()
        self.batch_appended.emit(len(self._apps))


class ApplicationFilterProxyModel(QSortFilterProxyModel):
    """Proxy model supporting search and platform/intent filtering."""

    def __init__(self) -> None:
        super().__init__()
        self._search_text: str = ""
        self._platform_filter: str | None = None
        self._intent_filter: str | None = None
        self._fuzzy_threshold: float = 0.62
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setDynamicSortFilter(True)

    def set_search_text(self, text: str) -> None:
        normalised = sanitize_search_text(text).lower()
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
                app.app_version if hasattr(app, "app_version") else None,
            ]
            tokens = [token for token in self._search_text.split() if token]
            blob = " ".join(
                value.lower() for value in haystack if isinstance(value, str)
            )
            matched = False
            if tokens and all(token in blob for token in tokens):
                matched = True
            else:
                best_ratio = 0.0
                for value in haystack:
                    if not isinstance(value, str) or not value:
                        continue
                    ratio = SequenceMatcher(
                        None, self._search_text, value.lower()
                    ).ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
                        if best_ratio >= 0.95:
                            break
                matched = best_ratio >= self._fuzzy_threshold
            if not matched:
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
