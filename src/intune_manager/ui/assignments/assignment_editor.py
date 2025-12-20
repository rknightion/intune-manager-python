from __future__ import annotations

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
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from intune_manager.data import (
    AssignmentFilter,
    AssignmentFilterType,
    AssignmentIntent,
    DirectoryGroup,
    MobileAppAssignment,
)
from intune_manager.data.models.assignment import (
    AllDevicesAssignmentTarget,
    AllLicensedUsersAssignmentTarget,
    GroupAssignmentTarget,
)
from intune_manager.utils.enums import enum_text


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
            self._filter_combo.addItem(
                assignment_filter.display_name or assignment_filter.id,
                assignment_filter.id,
            )
        form.addWidget(QLabel("Assignment filter"), 2, 0)
        form.addWidget(self._filter_combo, 2, 1)

        self._filter_mode_combo = QComboBox()
        self._filter_mode_combo.addItem("No filter", AssignmentFilterType.NONE.value)
        self._filter_mode_combo.addItem(
            "Include devices matching filter", AssignmentFilterType.INCLUDE.value
        )
        self._filter_mode_combo.addItem(
            "Exclude devices matching filter", AssignmentFilterType.EXCLUDE.value
        )
        form.addWidget(QLabel("Filter mode"), 3, 0)
        form.addWidget(self._filter_mode_combo, 3, 1)

        self._intent_combo = QComboBox()
        for intent in AssignmentIntent:
            self._intent_combo.addItem(intent.value, intent.value)
        form.addWidget(QLabel("Intent"), 4, 0)
        form.addWidget(self._intent_combo, 4, 1)

        layout.addLayout(form)

        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._button_box.accepted.connect(self._handle_accept)
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)

        self._target_type_combo.currentIndexChanged.connect(self._sync_inputs)
        self._filter_combo.currentIndexChanged.connect(self._sync_filter_mode)
        self._sync_inputs()
        self._sync_filter_mode()

    def assignment(self) -> MobileAppAssignment | None:
        return self._assignment

    def _sync_inputs(self) -> None:
        target_type = self._target_type_combo.currentData()
        is_group = target_type == "group"
        supports_filters = target_type in {"group", "all_devices"}
        has_groups = bool(self._groups)
        has_filters = bool(self._filters)
        self._group_combo.setEnabled(is_group and has_groups)
        self._filter_combo.setEnabled(supports_filters and has_filters)
        self._filter_mode_combo.setEnabled(supports_filters and has_filters)
        if not is_group:
            self._group_combo.setCurrentIndex(0)
        self._sync_filter_mode()

    def _sync_filter_mode(self) -> None:
        """Enable/disable filter mode based on whether a filter is selected."""
        filter_id = self._filter_combo.currentData()
        if filter_id is None:
            # No filter selected, disable filter mode and set to NONE
            self._filter_mode_combo.setEnabled(False)
            self._filter_mode_combo.setCurrentIndex(0)  # Set to "No filter"
        else:
            # Filter selected, enable filter mode
            self._filter_mode_combo.setEnabled(True)

    def _handle_accept(self) -> None:
        target_type = self._target_type_combo.currentData()
        filter_id = self._filter_combo.currentData()
        filter_mode_str = self._filter_mode_combo.currentData()
        filter_mode = (
            AssignmentFilterType(filter_mode_str)
            if filter_mode_str
            else AssignmentFilterType.NONE
        )

        # Validate: if filter is selected, mode must not be NONE
        if filter_id and filter_mode == AssignmentFilterType.NONE:
            QMessageBox.warning(
                self,
                "Missing filter mode",
                "Please select a filter mode (Include/Exclude) when using an assignment filter.",
            )
            return

        if target_type == "group":
            group_id = self._group_combo.currentData()
            if not group_id:
                QMessageBox.warning(
                    self, "Missing group", "Select a group target before continuing."
                )
                return

            # Always use GroupAssignmentTarget with filter fields
            target = GroupAssignmentTarget(
                group_id=group_id,
                assignment_filter_id=filter_id,
                assignment_filter_type=filter_mode,
            )
        else:
            target = AllDevicesAssignmentTarget(
                assignment_filter_id=filter_id,
                assignment_filter_type=filter_mode,
            )

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
        assignments: List[MobileAppAssignment],
        groups: List[DirectoryGroup],
        filters: List[AssignmentFilter],
        *,
        subject_name: str = "Assignments",
        on_export: AssignmentExportCallback | None = None,
        auto_export_default: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Assignment editor — {subject_name}")
        self.resize(860, 540)

        self._assignments: List[MobileAppAssignment] = list(assignments)
        self._groups = groups
        self._filters = filters
        self._group_lookup = {group.id: group for group in groups if group.id}
        self._filter_lookup = {
            assignment_filter.id: assignment_filter
            for assignment_filter in filters
            if assignment_filter.id
        }
        self._combos: list[QComboBox] = []
        self._export_callback = on_export

        layout = QVBoxLayout(self)
        header = QLabel(
            "Adjust assignment intents, add or remove targets, and configure filters.",
            parent=self,
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        self._table = QTableWidget(0, 5, parent=self)
        self._table.setHorizontalHeaderLabels(
            ["Target", "Intent", "Filter", "Filter Mode", "Type"]
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table, stretch=1)

        controls_layout = QHBoxLayout()
        self._add_button = QPushButton("Add target")
        self._remove_button = QPushButton("Remove target")
        controls_layout.addWidget(self._add_button)
        controls_layout.addWidget(self._remove_button)
        controls_layout.addStretch()
        layout.addLayout(controls_layout)

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

        self._auto_export_checkbox = QCheckBox(
            "Export assignments before applying", parent=self
        )
        self._auto_export_checkbox.setChecked(auto_export_default)
        layout.addWidget(self._auto_export_checkbox)

        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Save,
            parent=self,
        )
        self._export_button = QPushButton("Export JSON", parent=self)
        self._button_box.addButton(
            self._export_button, QDialogButtonBox.ButtonRole.ActionRole
        )
        layout.addWidget(self._button_box)

        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)
        self._export_button.clicked.connect(self._handle_export_clicked)
        self._add_button.clicked.connect(self._handle_add_assignment)
        self._remove_button.clicked.connect(self._handle_remove_assignment)
        self._table.currentCellChanged.connect(self._handle_selection_changed)

        self._rebuild_table()
        if self._table.rowCount() > 0:
            self._table.selectRow(0)

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

    def _handle_selection_changed(
        self, current_row: int, _current_col: int, _prev_row: int, _prev_col: int
    ) -> None:
        # Selection changed - no additional action needed now that settings/schedule removed
        pass

    def _rebuild_table(self) -> None:
        self._table.setRowCount(len(self._assignments))
        self._combos.clear()
        for row, assignment in enumerate(self._assignments):
            target_item = QTableWidgetItem(self._target_label(assignment))
            type_item = QTableWidgetItem(self._target_type_label(assignment))
            for item in (target_item, type_item):
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self._table.setItem(row, 0, target_item)

            # Intent combo
            intent_combo = QComboBox()
            for intent in AssignmentIntent:
                intent_combo.addItem(intent.value, intent.value)
            intent_combo.setCurrentText(enum_text(assignment.intent) or "")
            intent_combo.currentIndexChanged.connect(
                lambda _idx, row=row, widget=intent_combo: self._update_intent(
                    row, widget
                )
            )
            self._table.setCellWidget(row, 1, intent_combo)
            self._combos.append(intent_combo)

            # Filter combo (only for group assignments)
            filter_combo = QComboBox()
            filter_combo.addItem("No filter", None)
            for assignment_filter in self._filters:
                if not assignment_filter.id:
                    continue
                filter_combo.addItem(
                    assignment_filter.display_name or assignment_filter.id,
                    assignment_filter.id,
                )
            # Set current filter
            current_filter_id = getattr(assignment.target, "assignment_filter_id", None)
            if current_filter_id:
                index = filter_combo.findData(current_filter_id)
                if index >= 0:
                    filter_combo.setCurrentIndex(index)
            # Enable for targets that support assignment filters (groups + all devices)
            supports_filters = isinstance(
                assignment.target,
                (
                    GroupAssignmentTarget,
                    AllDevicesAssignmentTarget,
                    AllLicensedUsersAssignmentTarget,
                ),
            )
            filter_combo.setEnabled(supports_filters)
            filter_combo.currentIndexChanged.connect(
                lambda _idx, row=row, widget=filter_combo: self._update_filter(
                    row, widget
                )
            )
            self._table.setCellWidget(row, 2, filter_combo)
            self._combos.append(filter_combo)

            # Filter mode combo
            filter_mode_combo = QComboBox()
            filter_mode_combo.addItem("—", AssignmentFilterType.NONE.value)
            filter_mode_combo.addItem("Include", AssignmentFilterType.INCLUDE.value)
            filter_mode_combo.addItem("Exclude", AssignmentFilterType.EXCLUDE.value)
            # Set current filter mode
            current_filter_type = getattr(
                assignment.target, "assignment_filter_type", AssignmentFilterType.NONE
            )
            filter_type_str = (
                enum_text(current_filter_type)
                if current_filter_type
                else AssignmentFilterType.NONE.value
            )
            index = filter_mode_combo.findData(filter_type_str)
            if index >= 0:
                filter_mode_combo.setCurrentIndex(index)
            # Disable for targets that don't support filters or when no filter selected
            has_filter = current_filter_id is not None
            filter_mode_combo.setEnabled(supports_filters and has_filter)
            filter_mode_combo.currentIndexChanged.connect(
                lambda _idx,
                row=row,
                widget=filter_mode_combo: self._update_filter_mode(row, widget)
            )
            self._table.setCellWidget(row, 3, filter_mode_combo)
            self._combos.append(filter_mode_combo)

            self._table.setItem(row, 4, type_item)

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
        if selected == enum_text(assignment.intent):
            return
        self._assignments[row] = assignment.model_copy(
            update={"intent": AssignmentIntent(selected)}
        )

    def _update_filter(self, row: int, combo: QComboBox) -> None:
        """Update filter for a group assignment."""
        if row < 0 or row >= len(self._assignments):
            return
        assignment = self._assignments[row]
        target = assignment.target
        if not isinstance(
            target,
            (
                GroupAssignmentTarget,
                AllDevicesAssignmentTarget,
                AllLicensedUsersAssignmentTarget,
            ),
        ):
            return

        new_filter_id = combo.currentData()
        current_filter_id = getattr(target, "assignment_filter_id", None)

        if new_filter_id == current_filter_id:
            return

        # Update the target with new filter
        new_target = target.model_copy(update={"assignment_filter_id": new_filter_id})

        # If filter is being cleared, also clear the filter mode
        if new_filter_id is None:
            new_target = new_target.model_copy(
                update={"assignment_filter_type": AssignmentFilterType.NONE}
            )

        self._assignments[row] = assignment.model_copy(update={"target": new_target})

        # Update filter mode combo enabled state
        filter_mode_combo = self._table.cellWidget(row, 3)
        if isinstance(filter_mode_combo, QComboBox):
            filter_mode_combo.setEnabled(new_filter_id is not None)
            if new_filter_id is None:
                # Reset to NONE when filter cleared
                index = filter_mode_combo.findData(AssignmentFilterType.NONE.value)
                if index >= 0:
                    filter_mode_combo.setCurrentIndex(index)

    def _update_filter_mode(self, row: int, combo: QComboBox) -> None:
        """Update filter mode for a group assignment."""
        if row < 0 or row >= len(self._assignments):
            return
        assignment = self._assignments[row]
        target = assignment.target
        if not isinstance(
            target,
            (
                GroupAssignmentTarget,
                AllDevicesAssignmentTarget,
                AllLicensedUsersAssignmentTarget,
            ),
        ):
            return

        new_mode_str = combo.currentData()
        new_mode = (
            AssignmentFilterType(new_mode_str)
            if new_mode_str
            else AssignmentFilterType.NONE
        )
        current_mode = (
            getattr(target, "assignment_filter_type", None) or AssignmentFilterType.NONE
        )

        if new_mode == current_mode:
            return

        # Validate: if filter is set, mode must not be NONE
        if (
            getattr(target, "assignment_filter_id", None)
            and new_mode == AssignmentFilterType.NONE
        ):
            QMessageBox.warning(
                self,
                "Invalid filter mode",
                "Filter mode cannot be '—' when a filter is selected. Please choose Include or Exclude.",
            )
            # Reset combo to current valid value
            index = combo.findData(enum_text(current_mode))
            if index >= 0:
                combo.setCurrentIndex(index)
            return

        # Update the target with new filter mode
        new_target = target.model_copy(update={"assignment_filter_type": new_mode})
        self._assignments[row] = assignment.model_copy(update={"target": new_target})

    def _target_label(self, assignment: MobileAppAssignment) -> str:
        target = assignment.target
        group_id = getattr(target, "group_id", None)
        if isinstance(target, AllDevicesAssignmentTarget):
            return "All devices"
        if isinstance(target, AllLicensedUsersAssignmentTarget):
            return "All users"
        if group_id:
            group = self._group_lookup.get(group_id)
            if group:
                return (
                    group.display_name or group.mail or group.mail_nickname or group_id
                )
            return group_id
        return getattr(target, "odata_type", "Unknown target")

    def _filter_label(self, assignment: MobileAppAssignment) -> str:
        filter_id = getattr(assignment.target, "assignment_filter_id", None)
        if not filter_id:
            return "—"
        filter_obj = self._filter_lookup.get(filter_id)
        return (
            filter_obj.display_name
            if filter_obj and filter_obj.display_name
            else filter_id
        )

    def _filter_mode_label(self, assignment: MobileAppAssignment) -> str:
        """Get user-friendly label for filter mode."""
        filter_type = getattr(assignment.target, "assignment_filter_type", None)
        if not filter_type:
            return "—"

        # Handle both enum and string values
        filter_type_str = enum_text(filter_type) if filter_type else ""

        mode_labels = {
            "none": "—",
            "include": "Include",
            "exclude": "Exclude",
        }
        return mode_labels.get(filter_type_str.lower(), filter_type_str or "—")

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
