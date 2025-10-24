from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont

from intune_manager.data import AssignmentFilter, DirectoryGroup, MobileAppAssignment
from intune_manager.services.assignments import AssignmentDiff, AssignmentUpdate


def _intent_label(assignment: MobileAppAssignment) -> str:
    return assignment.intent.name.replace("_", " ").title()


def _target_label(
    assignment: MobileAppAssignment,
    groups: Dict[str, DirectoryGroup],
) -> tuple[str, bool]:
    target = assignment.target
    target_type = getattr(target, "odata_type", "")
    group_id = getattr(target, "group_id", None)

    if target_type.endswith("allDevicesAssignmentTarget"):
        return ("All devices", False)
    if target_type.endswith("allUsersAssignmentTarget"):
        return ("All users", False)
    if group_id:
        group = groups.get(group_id)
        if group:
            return (f"Group · {group.display_name}", False)
        return (f"Group · {group_id} (missing)", True)
    return (target_type or "Unknown target", False)


def _filter_label(
    assignment: MobileAppAssignment,
    filters: Dict[str, AssignmentFilter],
) -> tuple[str, bool]:
    filter_id = getattr(assignment.target, "assignment_filter_id", None)
    if not filter_id:
        return ("—", False)
    filter_obj = filters.get(filter_id)
    if filter_obj is None:
        return (f"Filter missing ({filter_id})", True)
    return (filter_obj.display_name or filter_id, False)


def _target_type_label(assignment: MobileAppAssignment) -> str:
    odata_type = getattr(assignment.target, "odata_type", "")
    if not odata_type:
        return "Unknown"
    return odata_type.replace("#microsoft.graph.", "")


@dataclass(slots=True)
class DiffSummary:
    app_id: str
    app_name: str
    creates: int
    updates: int
    deletes: int
    warnings: list[str]
    has_filters: bool = False

    @property
    def has_changes(self) -> bool:
        return any((self.creates, self.updates, self.deletes))


@dataclass(slots=True)
class DiffDetail:
    action: str
    target: str
    intent: str
    filter_label: str
    detail: str
    is_warning: bool = False
    current_payload: dict[str, Any] | None = None
    desired_payload: dict[str, Any] | None = None


class AssignmentTableModel(QAbstractTableModel):
    """Table model representing assignments for a single application."""

    _columns: Sequence[str] = ("Target", "Intent", "Filter", "Target type")

    def __init__(self) -> None:
        super().__init__()
        self._assignments: list[MobileAppAssignment] = []
        self._group_lookup: Dict[str, DirectoryGroup] = {}
        self._filter_lookup: Dict[str, AssignmentFilter] = {}

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # noqa: D401
        return 0 if parent and parent.isValid() else len(self._assignments)

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # noqa: D401
        return 0 if parent and parent.isValid() else len(self._columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: ANN001
        if not index.isValid():
            return None
        if index.row() >= len(self._assignments):
            return None

        assignment = self._assignments[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            column = index.column()
            if column == 0:
                label, _ = _target_label(assignment, self._group_lookup)
                return label
            if column == 1:
                return _intent_label(assignment)
            if column == 2:
                label, _ = _filter_label(assignment, self._filter_lookup)
                return label
            if column == 3:
                return _target_type_label(assignment)
        if role == Qt.ItemDataRole.ForegroundRole and index.column() in {0, 2}:
            if index.column() == 0:
                _, is_warning = _target_label(assignment, self._group_lookup)
            else:
                _, is_warning = _filter_label(assignment, self._filter_lookup)
            if is_warning:
                return QColor(Qt.GlobalColor.darkYellow)
        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):  # noqa: ANN001
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self._columns):
                return self._columns[section]
        return super().headerData(section, orientation, role)

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        base = super().flags(index)
        return base | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled

    def assignment_at(self, row: int) -> MobileAppAssignment | None:
        if 0 <= row < len(self._assignments):
            return self._assignments[row]
        return None

    def set_assignments(
        self,
        assignments: Iterable[MobileAppAssignment],
        *,
        group_lookup: Dict[str, DirectoryGroup],
        filter_lookup: Dict[str, AssignmentFilter],
    ) -> None:
        self.beginResetModel()
        self._assignments = list(assignments)
        self._group_lookup = dict(group_lookup)
        self._filter_lookup = dict(filter_lookup)
        self.endResetModel()


class DiffSummaryModel(QAbstractTableModel):
    """Model summarising diff results per target application."""

    _columns: Sequence[str] = (
        "Application",
        "Creates",
        "Updates",
        "Deletes",
        "Warnings",
    )

    def __init__(self) -> None:
        super().__init__()
        self._summaries: list[DiffSummary] = []

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # noqa: D401
        return 0 if parent and parent.isValid() else len(self._summaries)

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # noqa: D401
        return 0 if parent and parent.isValid() else len(self._columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: ANN001
        if not index.isValid():
            return None
        summary = self._summaries[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            column = index.column()
            if column == 0:
                return summary.app_name
            if column == 1:
                return f"{summary.creates:,}"
            if column == 2:
                return f"{summary.updates:,}"
            if column == 3:
                return f"{summary.deletes:,}"
            if column == 4:
                return "; ".join(summary.warnings) if summary.warnings else "—"
        if role == Qt.ItemDataRole.ForegroundRole and summary.warnings:
            return QColor(Qt.GlobalColor.darkYellow)
        if role == Qt.ItemDataRole.FontRole and summary.has_changes:
            font = QFont()
            font.setBold(True)
            return font
        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):  # noqa: ANN001
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(
            self._columns
        ):
            return self._columns[section]
        return super().headerData(section, orientation, role)

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        base = super().flags(index)
        return base | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled

    def summary_at(self, row: int) -> DiffSummary | None:
        if 0 <= row < len(self._summaries):
            return self._summaries[row]
        return None

    def set_summaries(self, summaries: Iterable[DiffSummary]) -> None:
        self.beginResetModel()
        self._summaries = list(summaries)
        self.endResetModel()


class DiffDetailModel(QAbstractTableModel):
    """Model detailing per-assignment operations for a selected diff."""

    _columns: Sequence[str] = ("Action", "Target", "Intent", "Filter", "Details")

    def __init__(self) -> None:
        super().__init__()
        self._details: list[DiffDetail] = []

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # noqa: D401
        return 0 if parent and parent.isValid() else len(self._details)

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # noqa: D401
        return 0 if parent and parent.isValid() else len(self._columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: ANN001
        if not index.isValid():
            return None
        detail = self._details[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            column = index.column()
            if column == 0:
                return detail.action
            if column == 1:
                return detail.target
            if column == 2:
                return detail.intent
            if column == 3:
                return detail.filter_label
            if column == 4:
                return detail.detail
        if role == Qt.ItemDataRole.ForegroundRole and detail.is_warning:
            return QColor(Qt.GlobalColor.darkYellow)
        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):  # noqa: ANN001
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(
            self._columns
        ):
            return self._columns[section]
        return super().headerData(section, orientation, role)

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        base = super().flags(index)
        return base | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled

    def set_details(self, details: Iterable[DiffDetail]) -> None:
        self.beginResetModel()
        self._details = list(details)
        self.endResetModel()

    def detail_at(self, row: int) -> DiffDetail | None:
        if 0 <= row < len(self._details):
            return self._details[row]
        return None

    @staticmethod
    def from_diff(
        diff: AssignmentDiff,
        *,
        groups: Dict[str, DirectoryGroup],
        filters: Dict[str, AssignmentFilter],
    ) -> List[DiffDetail]:
        details: list[DiffDetail] = []

        for assignment in diff.to_create:
            target, target_warning = _target_label(assignment, groups)
            filter_label, filter_warning = _filter_label(assignment, filters)
            details.append(
                DiffDetail(
                    action="Create",
                    target=target,
                    intent=_intent_label(assignment),
                    filter_label=filter_label,
                    detail="New target assignment",
                    is_warning=target_warning or filter_warning,
                    current_payload=None,
                    desired_payload=_assignment_payload(assignment),
                ),
            )

        for update in diff.to_update:
            detail_text = _describe_update(update)
            target, target_warning = _target_label(update.desired, groups)
            filter_label, filter_warning = _filter_label(update.desired, filters)
            details.append(
                DiffDetail(
                    action="Update",
                    target=target,
                    intent=_intent_label(update.desired),
                    filter_label=filter_label,
                    detail=detail_text,
                    is_warning=target_warning or filter_warning,
                    current_payload=_assignment_payload(update.current),
                    desired_payload=_assignment_payload(update.desired),
                ),
            )

        for assignment in diff.to_delete:
            target, target_warning = _target_label(assignment, groups)
            filter_label, filter_warning = _filter_label(assignment, filters)
            details.append(
                DiffDetail(
                    action="Delete",
                    target=target,
                    intent=_intent_label(assignment),
                    filter_label=filter_label,
                    detail="Remove existing assignment",
                    is_warning=target_warning or filter_warning,
                    current_payload=_assignment_payload(assignment),
                    desired_payload=None,
                ),
            )
        return details


def _assignment_payload(
    assignment: MobileAppAssignment | None,
) -> dict[str, Any] | None:
    if assignment is None:
        return None
    try:
        return assignment.to_graph()
    except Exception:  # noqa: BLE001 - fallback for unexpected serialization issues
        return None


def _describe_update(update: AssignmentUpdate) -> str:
    current = update.current
    desired = update.desired
    details: list[str] = []
    if current.intent != desired.intent:
        details.append(f"Intent {current.intent.value} → {desired.intent.value}")

    current_settings = current.settings.to_graph() if current.settings else {}
    desired_settings = desired.settings.to_graph() if desired.settings else {}
    if current_settings != desired_settings:
        details.append("Settings changed")

    return "; ".join(details) if details else "No payload change"


__all__ = [
    "AssignmentTableModel",
    "DiffSummary",
    "DiffSummaryModel",
    "DiffDetail",
    "DiffDetailModel",
]
