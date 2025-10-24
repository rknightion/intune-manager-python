from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable, Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QSortFilterProxyModel

from intune_manager.data import AuditEvent
from intune_manager.utils.sanitize import sanitize_search_text


def _format_timestamp(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _actor_summary(event: AuditEvent) -> str:
    actor = event.actor
    if actor is None:
        return "—"
    for candidate in [
        actor.user_principal_name,
        actor.service_principal_name,
        actor.application_display_name,
        actor.user_id,
        actor.type,
    ]:
        if candidate:
            return candidate
    return "—"


def _resource_summary(event: AuditEvent) -> str:
    resources = event.resources or []
    if not resources:
        return "—"
    primary = resources[0]
    for candidate in [primary.display_name, primary.resource_id, primary.type]:
        if candidate:
            return candidate
    return "—"


@dataclass(slots=True)
class AuditColumn:
    key: str
    header: str
    accessor: Callable[[AuditEvent], str]


class AuditEventTableModel(QAbstractTableModel):
    """Projection model for audit events."""

    def __init__(self, events: Sequence[AuditEvent] | None = None) -> None:
        super().__init__()
        self._events: list[AuditEvent] = list(events or [])
        self._columns: list[AuditColumn] = [
            AuditColumn(
                "timestamp",
                "Timestamp",
                lambda event: _format_timestamp(event.activity_date_time),
            ),
            AuditColumn("activity", "Activity", lambda event: event.activity or "—"),
            AuditColumn(
                "component", "Component", lambda event: event.component_name or "—"
            ),
            AuditColumn("result", "Result", lambda event: event.activity_result or "—"),
            AuditColumn("category", "Category", lambda event: event.category or "—"),
            AuditColumn("actor", "Actor", _actor_summary),
            AuditColumn("resource", "Resource", _resource_summary),
        ]

    # ----------------------------------------------------------------- Qt API

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        if parent and parent.isValid():
            return 0
        return len(self._events)

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        if parent and parent.isValid():
            return 0
        return len(self._columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802, ANN001
        if not index.isValid():
            return None
        row = index.row()
        column = index.column()
        if row < 0 or row >= len(self._events):
            return None
        event = self._events[row]

        if role == Qt.ItemDataRole.DisplayRole:
            accessor = self._columns[column].accessor
            return accessor(event)

        if role == Qt.ItemDataRole.UserRole:
            return event

        return None

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> str | None:
        if orientation != Qt.Orientation.Horizontal:
            return None if role == Qt.ItemDataRole.DisplayRole else None
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if section < 0 or section >= len(self._columns):
            return None
        return self._columns[section].header

    # ----------------------------------------------------------------- Helpers

    def set_events(self, events: Iterable[AuditEvent]) -> None:
        self.beginResetModel()
        self._events = list(events)
        self.endResetModel()

    def event_at(self, row: int) -> AuditEvent | None:
        if 0 <= row < len(self._events):
            return self._events[row]
        return None

    def events(self) -> list[AuditEvent]:
        return list(self._events)


class AuditEventFilterProxyModel(QSortFilterProxyModel):
    """Client-side filtering for audit events."""

    def __init__(self) -> None:
        super().__init__()
        self._search_text: str = ""
        self._category: str | None = None
        self._result: str | None = None
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    # ----------------------------------------------------------------- Setters

    def set_search_text(self, text: str) -> None:
        normalised = sanitize_search_text(text).lower()
        if self._search_text == normalised:
            return
        self._search_text = normalised
        self.invalidate()

    def set_category_filter(self, category: str | None) -> None:
        if category == "":
            category = None
        if self._category == category:
            return
        self._category = category
        self.invalidate()

    def set_result_filter(self, result: str | None) -> None:
        if result == "":
            result = None
        if self._result == result:
            return
        self._result = result
        self.invalidate()

    # --------------------------------------------------------- Filter logic

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:  # noqa: N802
        model = self.sourceModel()
        if model is None:
            return True
        index = model.index(source_row, 0, source_parent)
        event: AuditEvent | None = model.data(index, Qt.ItemDataRole.UserRole)
        if event is None:
            return True

        if self._category and (event.category or "").strip() != self._category:
            return False

        if self._result:
            result_value = (event.activity_result or "").strip()
            if self._result == "Success" and result_value.lower() != "success":
                return False
            if self._result == "Failure" and result_value.lower() == "success":
                return False
            if self._result == "Other" and result_value.lower() in {
                "success",
                "failure",
                "failed",
            }:
                return False

        if not self._search_text:
            return True

        haystack = " ".join(
            filter(
                None,
                [
                    event.activity,
                    event.display_name,
                    event.activity_operation_type,
                    event.activity_type,
                    event.component_name,
                    event.activity_result,
                    event.category,
                    event.correlation_id,
                    _actor_summary(event),
                    _resource_summary(event),
                ],
            ),
        ).lower()
        return self._search_text in haystack


__all__ = [
    "AuditEventTableModel",
    "AuditEventFilterProxyModel",
]
