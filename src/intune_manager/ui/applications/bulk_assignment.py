from __future__ import annotations

from dataclasses import dataclass
from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
)

from intune_manager.data import AssignmentFilter, DirectoryGroup, MobileApp
from intune_manager.data.models.assignment import (
    AssignmentFilterType,
    AssignmentIntent,
    AssignmentSettings,
)
from intune_manager.utils.sanitize import sanitize_search_text

ALL_DEVICES_ID = "__ALL_DEVICES__"
ALL_USERS_ID = "__ALL_USERS__"


@dataclass(slots=True)
class BulkAssignmentPlan:
    """Result structure representing a bulk assignment request."""

    apps: list[MobileApp]
    groups: list[DirectoryGroup]
    intent: AssignmentIntent
    filter_id: str | None
    filter_mode: AssignmentFilterType
    settings: AssignmentSettings | None = None

    def group_ids(self) -> list[str]:
        return [group.id for group in self.groups if group.id]


class BulkAssignmentDialog(QDialog):
    """Guided workflow for applying assignments to multiple applications."""

    def __init__(
        self,
        *,
        apps: List[MobileApp],
        groups: List[DirectoryGroup],
        filters: List[AssignmentFilter],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bulk assignment wizard")
        self.resize(720, 620)

        self._apps = [app for app in apps if app.id]
        special_groups = [
            DirectoryGroup.model_construct(
                id=ALL_DEVICES_ID,
                display_name="All devices",
            ),
            DirectoryGroup.model_construct(
                id=ALL_USERS_ID,
                display_name="All users",
            ),
        ]
        self._groups = special_groups + [group for group in groups if group.id]
        self._filters = filters
        self._plan: BulkAssignmentPlan | None = None

        layout = QVBoxLayout(self)
        header = QLabel(
            "Assign the selected applications to target groups. Configure the intent and optional filter to apply across all chosen apps.",
            parent=self,
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        layout.addWidget(self._build_app_section())
        layout.addWidget(self._build_group_section())
        layout.addWidget(self._build_configuration_section())

        self._summary_label = QLabel("", parent=self)
        self._summary_label.setStyleSheet("color: palette(mid);")
        layout.addWidget(self._summary_label)

        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok,
            parent=self,
        )
        self._apply_button = self._button_box.button(QDialogButtonBox.StandardButton.Ok)
        self._apply_button.setText("Apply assignments")
        self._apply_button.setEnabled(False)
        self._button_box.accepted.connect(self._handle_accept)
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)

        self._filter_combo.currentIndexChanged.connect(self._sync_filter_mode)
        self._sync_filter_mode()
        self._update_summary()

    # ------------------------------------------------------------------ Sections

    def _build_app_section(self) -> QGroupBox:
        box = QGroupBox("1. Applications", parent=self)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        self._app_search = QLineEdit(parent=box)
        self._app_search.setPlaceholderText("Filter applications…")
        self._app_search.textChanged.connect(self._filter_app_list)
        layout.addWidget(self._app_search)

        self._app_list = QListWidget(parent=box)
        self._app_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self._app_list.setMinimumHeight(160)
        self._app_list.itemChanged.connect(lambda *_: self._sync_state())

        self._populate_app_list()
        layout.addWidget(self._app_list, stretch=1)

        hint = QLabel(
            "Uncheck any applications that should be excluded from this bulk operation.",
            parent=box,
        )
        hint.setStyleSheet("color: palette(mid);")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        return box

    def _build_group_section(self) -> QGroupBox:
        box = QGroupBox("2. Target groups", parent=self)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        self._group_search = QLineEdit(parent=box)
        self._group_search.setPlaceholderText("Filter groups by name…")
        self._group_search.textChanged.connect(self._filter_group_list)
        layout.addWidget(self._group_search)

        self._group_list = QListWidget(parent=box)
        self._group_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self._group_list.setMinimumHeight(200)
        self._group_list.itemChanged.connect(lambda *_: self._sync_state())

        self._populate_group_list()
        layout.addWidget(self._group_list, stretch=1)

        hint = QLabel(
            "Select one or more groups that should receive the chosen assignment intent.",
            parent=box,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid);")
        layout.addWidget(hint)

        return box

    def _build_configuration_section(self) -> QGroupBox:
        box = QGroupBox("3. Assignment configuration", parent=self)
        layout = QFormLayout(box)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self._intent_combo = QComboBox(parent=box)
        for intent in AssignmentIntent:
            if intent == AssignmentIntent.UNKNOWN:
                continue
            label = intent.value
            layout_label = label.replace(
                "availableWithoutEnrollment", "available (BYOD)"
            )
            self._intent_combo.addItem(layout_label, intent.value)
        self._intent_combo.setCurrentIndex(0)
        self._intent_combo.currentIndexChanged.connect(
            lambda *_: self._update_summary()
        )
        layout.addRow("Assignment intent", self._intent_combo)

        self._filter_combo = QComboBox(parent=box)
        self._filter_combo.addItem("No assignment filter", None)
        for assignment_filter in self._filters:
            if not assignment_filter.id:
                continue
            label = assignment_filter.display_name or assignment_filter.id
            self._filter_combo.addItem(label, assignment_filter.id)
        layout.addRow("Assignment filter", self._filter_combo)

        self._filter_mode_combo = QComboBox(parent=box)
        self._filter_mode_combo.addItem("No filter", AssignmentFilterType.NONE.value)
        self._filter_mode_combo.addItem(
            "Include devices matching filter", AssignmentFilterType.INCLUDE.value
        )
        self._filter_mode_combo.addItem(
            "Exclude devices matching filter", AssignmentFilterType.EXCLUDE.value
        )
        layout.addRow("Filter mode", self._filter_mode_combo)

        return box

    # ------------------------------------------------------------------- Populate

    def _populate_app_list(self) -> None:
        self._app_list.blockSignals(True)
        self._app_list.clear()
        for app in self._apps:
            label = app.display_name or app.id
            item = QListWidgetItem(label, self._app_list)
            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
            )
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, app)
            subtitle_parts = [app.owner or "", app.publisher or ""]
            subtitle = " · ".join(part for part in subtitle_parts if part)
            if subtitle:
                item.setToolTip(subtitle)
        self._app_list.blockSignals(False)

    def _populate_group_list(self) -> None:
        self._group_list.blockSignals(True)
        self._group_list.clear()
        for group in self._groups:
            label = group.display_name or group.mail or group.mail_nickname or group.id
            item = QListWidgetItem(label, self._group_list)
            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
            )
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, group)
            tooltip_parts = [
                f"Mail: {group.mail}" if group.mail else "",
                f"Type: {group.group_types}" if group.group_types else "",
            ]
            tooltip = "\n".join(part for part in tooltip_parts if part)
            if tooltip:
                item.setToolTip(tooltip)
        self._group_list.blockSignals(False)

    # ------------------------------------------------------------------- Filters

    def _filter_app_list(self, text: str) -> None:
        needle = sanitize_search_text(text).lower()
        for index in range(self._app_list.count()):
            item = self._app_list.item(index)
            matches = not needle or needle in item.text().lower()
            item.setHidden(not matches)
        self._update_summary()

    def _filter_group_list(self, text: str) -> None:
        needle = sanitize_search_text(text).lower()
        for index in range(self._group_list.count()):
            item = self._group_list.item(index)
            label = item.text().lower()
            tooltip = (item.toolTip() or "").lower()
            matches = not needle or needle in label or needle in tooltip
            item.setHidden(not matches)
        self._sync_state()

    # ------------------------------------------------------------------ Helpers

    def _selected_apps(self) -> list[MobileApp]:
        apps: list[MobileApp] = []
        for index in range(self._app_list.count()):
            item = self._app_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                app = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(app, MobileApp):
                    apps.append(app)
        return apps

    def _selected_groups(self) -> list[DirectoryGroup]:
        groups: list[DirectoryGroup] = []
        for index in range(self._group_list.count()):
            item = self._group_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                group = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(group, DirectoryGroup):
                    groups.append(group)
        return groups

    def _sync_state(self) -> None:
        self._update_summary()
        apps = self._selected_apps()
        groups = self._selected_groups()
        self._apply_button.setEnabled(bool(apps) and bool(groups))

    def _update_summary(self) -> None:
        apps = len(self._selected_apps())
        groups = len(self._selected_groups())
        intent_label = self._intent_combo.currentText()
        summary = (
            f"{apps} application(s) → {groups} group(s) with intent {intent_label}"
        )
        self._summary_label.setText(summary)

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

    # ----------------------------------------------------------------- Dialog API

    def plan(self) -> BulkAssignmentPlan | None:
        return self._plan

    # ------------------------------------------------------------------ Lifecycle

    def _handle_accept(self) -> None:
        apps = self._selected_apps()
        groups = self._selected_groups()
        if not apps:
            QMessageBox.warning(
                self,
                "No applications",
                "Select at least one application before continuing.",
            )
            return
        if not groups:
            QMessageBox.warning(
                self, "No groups", "Select at least one target group before continuing."
            )
            return

        intent_value = self._intent_combo.currentData()
        intent = AssignmentIntent(intent_value)
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

        self._plan = BulkAssignmentPlan(
            apps=apps,
            groups=groups,
            intent=intent,
            filter_id=filter_id,
            filter_mode=filter_mode,
        )
        self.accept()
