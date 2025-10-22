from __future__ import annotations

import json
from typing import Callable, Iterable, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from pydantic import ValidationError

from intune_manager.data import (
    AssignmentFilter,
    AssignmentIntent,
    AssignmentSettings,
    DirectoryGroup,
    MobileApp,
    MobileAppAssignment,
)
from intune_manager.data.models.assignment import (
    AllDevicesAssignmentTarget,
    FilteredGroupAssignmentTarget,
    GroupAssignmentTarget,
)


AssignmentExportCallback = Callable[[Iterable[MobileAppAssignment]], None]


class AssignmentCreateDialog(QDialog):
    """Dialog allowing creation of a new assignment target."""

    def __init__(
        self,
        groups: List[DirectoryGroup],
        filters: List[AssignmentFilter],
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add assignment target")
        self.resize(460, 260)
        self._groups = groups
        self._filters = filters
        self._assignment: MobileAppAssignment | None = None

        layout = QVBoxLayout(self)
        form = QGridLayout()
        form.setSpacing(8)

        self._target_type_combo = QComboBox()
        self._target_type_combo.addItem("All devices", "all_devices")
        self._target_type_combo.addItem("Specific group", "group")
        form.addWidget(QLabel("Target type"), 0, 0)
        form.addWidget(self._target_type_combo, 0, 1)

        self._group_combo = QComboBox()
        self._group_combo.addItem("Select group…", None)
        for group in groups:
            if not group.id:
                continue
            label = group.display_name or group.mail or group.mail_nickname or group.id
            self._group_combo.addItem(label, group.id)
        form.addWidget(QLabel("Group"), 1, 0)
        form.addWidget(self._group_combo, 1, 1)

        self._filter_combo = QComboBox()
        self._filter_combo.addItem("No filter", None)
        for assignment_filter in filters:
            if not assignment_filter.id:
                continue
            self._filter_combo.addItem(assignment_filter.display_name or assignment_filter.id, assignment_filter.id)
        form.addWidget(QLabel("Assignment filter"), 2, 0)
        form.addWidget(self._filter_combo, 2, 1)

        self._intent_combo = QComboBox()
        for intent in AssignmentIntent:
            self._intent_combo.addItem(intent.value, intent.value)
        form.addWidget(QLabel("Intent"), 3, 0)
        form.addWidget(self._intent_combo, 3, 1)

        layout.addLayout(form)

        self._button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self._button_box.accepted.connect(self._handle_accept)
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)

        self._target_type_combo.currentIndexChanged.connect(self._sync_inputs)
        self._sync_inputs()

    def assignment(self) -> MobileAppAssignment | None:
        return self._assignment

    def _sync_inputs(self) -> None:
        is_group = self._target_type_combo.currentData() == "group"
        has_groups = bool(self._groups)
        self._group_combo.setEnabled(is_group and has_groups)
        self._filter_combo.setEnabled(is_group and bool(self._filters))

    def _handle_accept(self) -> None:
        target_type = self._target_type_combo.currentData()
        if target_type == "group":
            group_id = self._group_combo.currentData()
            if not group_id:
                QMessageBox.warning(self, "Missing group", "Select a group target before continuing.")
                return
            filter_id = self._filter_combo.currentData()
            if filter_id:
                target = FilteredGroupAssignmentTarget(group_id=group_id, assignment_filter_id=filter_id)
            else:
                target = GroupAssignmentTarget(group_id=group_id)
        else:
            target = AllDevicesAssignmentTarget()

        intent_value = self._intent_combo.currentData()
        intent = AssignmentIntent(intent_value)
        assignment = MobileAppAssignment.model_construct(
            id="",
            intent=intent,
            target=target,
            settings=None,
        )
        self._assignment = assignment
        self.accept()


class AssignmentEditorDialog(QDialog):
    """Assignment editor supporting intent updates and target management."""

    def __init__(
        self,
        app: MobileApp,
        assignments: List[MobileAppAssignment],
        groups: List[DirectoryGroup],
        filters: List[AssignmentFilter],
        *,
        on_export: AssignmentExportCallback | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Assignment editor — {app.display_name}")
        self.resize(860, 540)

        self._assignments: List[MobileAppAssignment] = list(assignments)
        self._groups = groups
        self._filters = filters
        self._group_lookup = {group.id: group for group in groups if group.id}
        self._filter_lookup = {assignment_filter.id: assignment_filter for assignment_filter in filters if assignment_filter.id}
        self._combos: list[QComboBox] = []
        self._export_callback = on_export
        self._updating_settings = False

        layout = QVBoxLayout(self)
        header = QLabel(
            "Adjust assignment intents, add or remove targets, and optionally tweak advanced settings.",
            parent=self,
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        self._table = QTableWidget(0, 4, parent=self)
        self._table.setHorizontalHeaderLabels(["Target", "Intent", "Filter", "Type"])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table, stretch=1)

        controls_layout = QHBoxLayout()
        self._add_button = QPushButton("Add target")
        self._remove_button = QPushButton("Remove target")
        self._apply_settings_button = QPushButton("Apply settings")
        controls_layout.addWidget(self._add_button)
        controls_layout.addWidget(self._remove_button)
        controls_layout.addStretch()
        controls_layout.addWidget(self._apply_settings_button)
        layout.addLayout(controls_layout)

        settings_box = QGroupBox("Assignment settings (JSON)")
        settings_layout = QVBoxLayout(settings_box)
        settings_hint = QLabel("Paste Graph assignment settings payloads (optional). Leave empty for defaults.")
        settings_hint.setWordWrap(True)
        settings_hint.setStyleSheet("color: palette(mid);")
        settings_layout.addWidget(settings_hint)
        self._settings_edit = QPlainTextEdit()
        settings_layout.addWidget(self._settings_edit, stretch=1)
        layout.addWidget(settings_box, stretch=1)

        helper_box = QGroupBox("Tips")
        helper_layout = QGridLayout(helper_box)
        helper_layout.setContentsMargins(12, 8, 12, 8)
        helper_layout.addWidget(
            QLabel(
                "Assignments update immediately on apply. Consider exporting a backup first.",
                parent=helper_box,
            ),
            0,
            0,
        )
        layout.addWidget(helper_box)

        self._auto_export_checkbox = QCheckBox("Export assignments before applying", parent=self)
        self._auto_export_checkbox.setChecked(True)
        layout.addWidget(self._auto_export_checkbox)

        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save,
            parent=self,
        )
        self._export_button = QPushButton("Export JSON", parent=self)
        self._button_box.addButton(self._export_button, QDialogButtonBox.ButtonRole.ActionRole)
        layout.addWidget(self._button_box)

        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)
        self._export_button.clicked.connect(self._handle_export_clicked)
        self._add_button.clicked.connect(self._handle_add_assignment)
        self._remove_button.clicked.connect(self._handle_remove_assignment)
        self._apply_settings_button.clicked.connect(self._apply_settings_clicked)
        self._table.currentCellChanged.connect(self._handle_selection_changed)

        self._rebuild_table()
        if self._table.rowCount() > 0:
            self._table.selectRow(0)
            self._load_settings_for_row(0)

    # ----------------------------------------------------------------- Helpers

    def desired_assignments(self) -> List[MobileAppAssignment]:
        return list(self._assignments)

    def auto_export_enabled(self) -> bool:
        return self._auto_export_checkbox.isChecked()

    def _handle_export_clicked(self) -> None:
        if self._export_callback is None:
            return
        self._export_callback(self.desired_assignments())

    def _handle_add_assignment(self) -> None:
        dialog = AssignmentCreateDialog(self._groups, self._filters, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        assignment = dialog.assignment()
        if assignment is None:
            return
        self._assignments.append(assignment)
        self._rebuild_table()
        row = self._table.rowCount() - 1
        if row >= 0:
            self._table.selectRow(row)
            self._load_settings_for_row(row)

    def _handle_remove_assignment(self) -> None:
        row = self._selected_row()
        if row is None:
            QMessageBox.information(self, "No selection", "Select a target to remove.")
            return
        self._assignments.pop(row)
        self._rebuild_table()
        if self._table.rowCount() > 0:
            new_row = min(row, self._table.rowCount() - 1)
            self._table.selectRow(new_row)
            self._load_settings_for_row(new_row)
        else:
            self._settings_edit.clear()

    def _apply_settings_clicked(self) -> None:
        row = self._selected_row()
        if row is None:
            QMessageBox.information(self, "No selection", "Select a target before applying settings.")
            return
        text = self._settings_edit.toPlainText().strip()
        if not text:
            self._assignments[row] = self._assignments[row].model_copy(update={"settings": None})
            QMessageBox.information(self, "Settings cleared", "Advanced settings removed for the selected assignment.")
            return
        try:
            payload = json.loads(text)
            settings = AssignmentSettings.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            QMessageBox.warning(self, "Invalid settings", f"Unable to parse settings JSON: {exc}")
            return
        self._assignments[row] = self._assignments[row].model_copy(update={"settings": settings})
        QMessageBox.information(self, "Settings updated", "Advanced settings applied to the selected assignment.")

    def _handle_selection_changed(self, current_row: int, _current_col: int, _prev_row: int, _prev_col: int) -> None:
        if current_row < 0:
            self._settings_edit.clear()
            return
        self._load_settings_for_row(current_row)

    def _load_settings_for_row(self, row: int) -> None:
        if row < 0 or row >= len(self._assignments):
            self._settings_edit.clear()
            return
        assignment = self._assignments[row]
        self._updating_settings = True
        try:
            payload = assignment.settings.to_graph() if assignment.settings else {}
            self._settings_edit.setPlainText(json.dumps(payload, indent=2) if payload else "")
        finally:
            self._updating_settings = False

    def _rebuild_table(self) -> None:
        self._table.setRowCount(len(self._assignments))
        self._combos.clear()
        for row, assignment in enumerate(self._assignments):
            target_item = QTableWidgetItem(self._target_label(assignment))
            filter_item = QTableWidgetItem(self._filter_label(assignment))
            type_item = QTableWidgetItem(self._target_type_label(assignment))
            for item in (target_item, filter_item, type_item):
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self._table.setItem(row, 0, target_item)
            combo = QComboBox()
            for intent in AssignmentIntent:
                combo.addItem(intent.value, intent.value)
            combo.setCurrentText(assignment.intent.value)
            combo.currentIndexChanged.connect(lambda _idx, row=row, widget=combo: self._update_intent(row, widget))
            self._table.setCellWidget(row, 1, combo)
            self._combos.append(combo)
            self._table.setItem(row, 2, filter_item)
            self._table.setItem(row, 3, type_item)

        self._table.resizeColumnsToContents()
        self._table.horizontalHeader().setStretchLastSection(True)

    def _selected_row(self) -> int | None:
        selection = self._table.selectionModel()
        if selection is None:
            return None
        indexes = selection.selectedRows()
        if not indexes:
            return None
        return indexes[0].row()

    def _update_intent(self, row: int, combo: QComboBox) -> None:
        if row < 0 or row >= len(self._assignments):
            return
        selected = combo.currentData()
        assignment = self._assignments[row]
        if selected == assignment.intent.value:
            return
        self._assignments[row] = assignment.model_copy(update={"intent": AssignmentIntent(selected)})

    def _target_label(self, assignment: MobileAppAssignment) -> str:
        target = assignment.target
        group_id = getattr(target, "group_id", None)
        if isinstance(target, AllDevicesAssignmentTarget):
            return "All devices"
        if group_id:
            group = self._group_lookup.get(group_id)
            if group:
                return group.display_name or group.mail or group.mail_nickname or group_id
            return group_id
        return getattr(target, "odata_type", "Unknown target")

    def _filter_label(self, assignment: MobileAppAssignment) -> str:
        filter_id = getattr(assignment.target, "assignment_filter_id", None)
        if not filter_id:
            return "—"
        filter_obj = self._filter_lookup.get(filter_id)
        return filter_obj.display_name if filter_obj and filter_obj.display_name else filter_id

    def _target_type_label(self, assignment: MobileAppAssignment) -> str:
        odata_type = getattr(assignment.target, "odata_type", "")
        if odata_type.startswith("#microsoft.graph."):
            return odata_type.split(".")[-1]
        return odata_type or "Unknown"


__all__ = [
    "AssignmentEditorDialog",
    "AssignmentExportCallback",
    "AssignmentCreateDialog",
]
