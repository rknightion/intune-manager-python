from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableView,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from intune_manager.data import AssignmentFilter, DirectoryGroup, MobileApp, MobileAppAssignment
from intune_manager.services.assignments import AssignmentDiff, AssignmentUpdate

from .models import DiffDetail, DiffDetailModel, DiffSummary, DiffSummaryModel


AssignmentDiffMap = Dict[str, AssignmentDiff]
WarningProvider = Callable[[str, AssignmentDiff], List[str]]


@dataclass(slots=True)
class BulkWizardOptions:
    notify_end_users: bool = False
    skip_warnings: bool = False
    retry_conflicts: bool = True


@dataclass(slots=True)
class BulkAssignmentPlan:
    diffs: AssignmentDiffMap
    options: BulkWizardOptions
    selected_app_ids: List[str]
    selected_group_ids: Set[str]
    warnings: List[str] = field(default_factory=list)


@dataclass(slots=True)
class _ConflictDescriptor:
    app_id: str
    app_name: str
    update: AssignmentUpdate
    group_label: str


class _ConflictRow(QWidget):
    def __init__(self, descriptor: _ConflictDescriptor, *, default_apply: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.descriptor = descriptor

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        summary = QLabel(
            f"{descriptor.app_name}: {descriptor.group_label} — {descriptor.update.current.intent} → {descriptor.update.desired.intent}",
        )
        summary.setWordWrap(True)
        summary.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(summary, stretch=1)

        self._choice = QComboBox()
        self._choice.addItem("Apply desired change", True)
        self._choice.addItem("Keep existing assignment", False)
        index = 0 if default_apply else 1
        self._choice.setCurrentIndex(index)
        layout.addWidget(self._choice, stretch=0)

    @property
    def apply(self) -> bool:
        return bool(self._choice.currentData())


class _ScrollContainer(QWidget):
    """Utility container that provides a scroll area for dynamic content."""

    def __init__(self, child: QWidget, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(child)
        layout.addWidget(scroll)


class BulkAssignmentWizard(QWizard):
    """Multi-step workflow for coordinating assignment updates across many apps."""

    def __init__(
        self,
        *,
        diffs: AssignmentDiffMap,
        apps: Dict[str, MobileApp],
        group_lookup: Dict[str, DirectoryGroup],
        desired_assignments: Iterable[MobileAppAssignment],
        warning_provider: WarningProvider | None = None,
        staged_groups: Dict[str, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._diffs = diffs
        self._apps = apps
        self._group_lookup = group_lookup
        self._desired_assignments = list(desired_assignments)
        self._warning_provider = warning_provider
        self._staged_groups = staged_groups or {}

        self._selected_app_ids: List[str] = list(diffs.keys())
        self._group_filter_active = False
        self._selected_group_ids: Set[str] = self._initial_group_ids()
        self._options = BulkWizardOptions()
        self._conflict_choices: Dict[Tuple[str, str], bool] = {}

        self._summary_model = DiffSummaryModel()
        self._detail_model = DiffDetailModel()
        self._warnings: List[str] = []

        self.setWindowTitle("Bulk assignment wizard")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)

        self._apps_page = _SelectAppsPage(self)
        self._groups_page = _SelectGroupsPage(self)
        self._settings_page = _ConfigureSettingsPage(self)
        self._preview_page = _PreviewPage(self)

        self.addPage(self._apps_page)
        self.addPage(self._groups_page)
        self.addPage(self._settings_page)
        self.addPage(self._preview_page)

    # ------------------------------------------------------------------ State

    def selected_app_ids(self) -> List[str]:
        return list(self._selected_app_ids)

    def set_selected_app_ids(self, app_ids: List[str]) -> None:
        self._selected_app_ids = app_ids
        self._settings_page.invalidate_conflicts()

    def selected_group_ids(self) -> Set[str]:
        return set(self._selected_group_ids)

    def set_selected_group_ids(self, group_ids: Set[str], *, filter_active: bool) -> None:
        self._selected_group_ids = group_ids
        self._group_filter_active = filter_active
        self._settings_page.invalidate_conflicts()

    def options(self) -> BulkWizardOptions:
        return self._options

    def set_options(
        self,
        *,
        notify_end_users: bool | None = None,
        skip_warnings: bool | None = None,
        retry_conflicts: bool | None = None,
    ) -> None:
        if notify_end_users is not None:
            self._options.notify_end_users = notify_end_users
        if skip_warnings is not None:
            self._options.skip_warnings = skip_warnings
        if retry_conflicts is not None:
            self._options.retry_conflicts = retry_conflicts

    def set_conflict_choice(self, app_id: str, assignment_id: str | None, apply_change: bool) -> None:
        key = (app_id, assignment_id or "")
        self._conflict_choices[key] = apply_change

    def conflict_choice(self, app_id: str, assignment_id: str | None) -> bool:
        key = (app_id, assignment_id or "")
        return self._conflict_choices.get(key, True)

    def available_diffs(self) -> AssignmentDiffMap:
        return self._diffs

    def app_label(self, app_id: str) -> str:
        app = self._apps.get(app_id)
        return app.display_name or app_id if app else app_id

    def group_label(self, group_id: str | None) -> str:
        if group_id is None:
            return "All users / platform"
        group = self._group_lookup.get(group_id)
        if group and group.display_name:
            return group.display_name
        staged_label = self._staged_groups.get(group_id)
        if staged_label:
            return f"{staged_label} (staged)"
        return group_id

    def desired_groups(self) -> Set[str]:
        ids: Set[str] = set()
        for assignment in self._desired_assignments:
            group_id = getattr(assignment.target, "group_id", None)
            if group_id:
                ids.add(group_id)
        ids.update(self._staged_groups.keys())
        return ids

    def _initial_group_ids(self) -> Set[str]:
        return self.desired_groups()

    def staged_group_ids(self) -> Set[str]:
        return set(self._staged_groups.keys())

    # ---------------------------------------------------------------- Preview

    def rebuild_preview(self) -> None:
        filtered = self.filtered_diffs()
        summaries: List[DiffSummary] = []
        warnings: List[str] = []

        for app_id, diff in filtered.items():
            app_label = self.app_label(app_id)
            diff_warnings = self._warning_provider(app_id, diff) if self._warning_provider else []
            summaries.append(
                DiffSummary(
                    app_id=app_id,
                    app_name=app_label,
                    creates=len(diff.to_create),
                    updates=len(diff.to_update),
                    deletes=len(diff.to_delete),
                    warnings=diff_warnings,
                    has_filters=any(
                        getattr(item.target, "assignment_filter_id", None)
                        for item in diff.to_create + [update.desired for update in diff.to_update]
                    ),
                ),
            )
            warnings.extend(f"{app_label}: {warning}" for warning in diff_warnings)

        self._warnings = warnings
        self._summary_model.set_summaries(summaries)

        details: List[DiffDetail] = []
        filter_lookup: Dict[str, AssignmentFilter] = {}
        for summary in summaries:
            diff = filtered.get(summary.app_id)
            if diff is None:
                continue
            details.extend(
                DiffDetailModel.from_diff(
                    diff,
                    groups=self._group_lookup,
                    filters=filter_lookup,
                ),
            )
        self._detail_model.set_details(details)

    def summary_model(self) -> DiffSummaryModel:
        return self._summary_model

    def detail_model(self) -> DiffDetailModel:
        return self._detail_model

    def preview_warnings(self) -> List[str]:
        return list(self._warnings)

    # ---------------------------------------------------------------- Diffs

    def filtered_diffs(self) -> AssignmentDiffMap:
        results: AssignmentDiffMap = {}
        for app_id in self._selected_app_ids:
            diff = self._diffs.get(app_id)
            if diff is None:
                continue
            filtered = self._filter_diff(app_id, diff, respect_conflicts=True)
            if filtered.is_noop:
                continue
            results[app_id] = filtered
        return results

    def _filter_diff(
        self,
        app_id: str,
        diff: AssignmentDiff,
        *,
        respect_conflicts: bool,
    ) -> AssignmentDiff:
        group_ids = self._selected_group_ids if self._group_filter_active else None

        def include_assignment(assignment: MobileAppAssignment) -> bool:
            if not group_ids:
                return True
            group_id = getattr(assignment.target, "group_id", None)
            return group_id is None or group_id in group_ids

        def include_update(update: AssignmentUpdate) -> bool:
            choice = self.conflict_choice(app_id, update.current.id) if respect_conflicts else True
            if not choice:
                return False
            if not group_ids:
                return True
            group_id = getattr(update.desired.target, "group_id", None)
            if group_id is not None and group_id not in group_ids:
                return False
            return True

        creates = [assignment for assignment in diff.to_create if include_assignment(assignment)]
        updates = [AssignmentUpdate(current=upd.current, desired=upd.desired) for upd in diff.to_update if include_update(upd)]

        deletes: List[MobileAppAssignment] = []
        for assignment in diff.to_delete:
            if not group_ids:
                deletes.append(assignment)
            else:
                group_id = getattr(assignment.target, "group_id", None)
                if group_id is None or group_id in group_ids:
                    deletes.append(assignment)

        return AssignmentDiff(
            to_create=creates,
            to_update=updates,
            to_delete=deletes,
        )

    # -------------------------------------------------------------- Conflicts

    def conflict_descriptors(self) -> List[_ConflictDescriptor]:
        descriptors: List[_ConflictDescriptor] = []
        for app_id in self._selected_app_ids:
            diff = self._diffs.get(app_id)
            if diff is None:
                continue
            filtered = self._filter_diff(app_id, diff, respect_conflicts=False)
            if filtered.is_noop:
                continue
            app_name = self.app_label(app_id)
            for update in filtered.to_update:
                group_id = getattr(update.desired.target, "group_id", None)
                descriptors.append(
                    _ConflictDescriptor(
                        app_id=app_id,
                        app_name=app_name,
                        update=update,
                        group_label=self.group_label(group_id),
                    ),
                )
        return descriptors

    # ---------------------------------------------------------------- Result

    def result(self) -> Optional[BulkAssignmentPlan]:
        diffs = self.filtered_diffs()
        if not diffs:
            return None
        return BulkAssignmentPlan(
            diffs=diffs,
            options=self._options,
            selected_app_ids=self.selected_app_ids(),
            selected_group_ids=self.selected_group_ids() if self._group_filter_active else set(),
            warnings=self.preview_warnings(),
        )


class _SelectAppsPage(QWizardPage):
    def __init__(self, wizard: BulkAssignmentWizard) -> None:
        super().__init__(wizard)
        self._wizard = wizard
        self.setTitle("Step 1 — Select target applications")
        self.setSubTitle("Choose which applications should receive the desired assignment changes.")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        layout.addWidget(self._list)

        button_row = QHBoxLayout()
        select_all = QPushButton("Select all")
        select_all.clicked.connect(self._handle_select_all)
        clear = QPushButton("Clear")
        clear.clicked.connect(self._handle_clear)
        button_row.addWidget(select_all)
        button_row.addWidget(clear)
        button_row.addStretch()
        layout.addLayout(button_row)

        self.setLayout(layout)

    def initializePage(self) -> None:
        self._populate()

    def _populate(self) -> None:
        selected = set(self._wizard.selected_app_ids())
        self._list.clear()
        for app_id, diff in self._wizard.available_diffs().items():
            label = self._wizard.app_label(app_id)
            item = QListWidgetItem(f"{label} — {len(diff.to_create)} add / {len(diff.to_update)} update / {len(diff.to_delete)} remove")
            item.setData(Qt.ItemDataRole.UserRole, app_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if app_id in selected else Qt.CheckState.Unchecked)
            self._list.addItem(item)

    def validatePage(self) -> bool:
        selected = []
        for index in range(self._list.count()):
            item = self._list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                app_id = item.data(Qt.ItemDataRole.UserRole)
                if app_id:
                    selected.append(app_id)
        if not selected:
            return False
        self._wizard.set_selected_app_ids(selected)
        return True

    def _handle_select_all(self) -> None:
        for index in range(self._list.count()):
            self._list.item(index).setCheckState(Qt.CheckState.Checked)

    def _handle_clear(self) -> None:
        for index in range(self._list.count()):
            self._list.item(index).setCheckState(Qt.CheckState.Unchecked)


class _SelectGroupsPage(QWizardPage):
    def __init__(self, wizard: BulkAssignmentWizard) -> None:
        super().__init__(wizard)
        self._wizard = wizard
        self.setTitle("Step 2 — Select target groups")
        self.setSubTitle("Limit the bulk operation to specific groups or filters if required.")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        layout.addWidget(self._list, stretch=1)

        helper = QLabel(
            "If all groups remain selected the full desired assignment payload will be applied. "
            "Clear specific groups to exclude them from the operation.",
        )
        helper.setWordWrap(True)
        helper.setStyleSheet("color: palette(mid);")
        layout.addWidget(helper)

        button_row = QHBoxLayout()
        select_all = QPushButton("Include all")
        select_all.clicked.connect(self._handle_select_all)
        clear = QPushButton("Include staged only")
        clear.clicked.connect(self._handle_select_staged)
        button_row.addWidget(select_all)
        button_row.addWidget(clear)
        button_row.addStretch()
        layout.addLayout(button_row)

        self.setLayout(layout)

    def initializePage(self) -> None:
        self._populate()

    def validatePage(self) -> bool:
        selected: Set[str] = set()
        total = 0
        for index in range(self._list.count()):
            item = self._list.item(index)
            if not item.flags() & Qt.ItemFlag.ItemIsEnabled:
                continue
            total += 1
            if item.checkState() == Qt.CheckState.Checked:
                value = item.data(Qt.ItemDataRole.UserRole)
                if value:
                    selected.add(value)
        filter_active = len(selected) != total and total > 0
        self._wizard.set_selected_group_ids(selected, filter_active=filter_active)
        return True

    def _populate(self) -> None:
        desired = self._wizard.desired_groups()
        selected = self._wizard.selected_group_ids()
        self._list.clear()
        if not desired:
            placeholder = QListWidgetItem("Assignments target all users/platforms; no groups to filter.")
            placeholder.setFlags(Qt.ItemFlag.ItemIsEnabled)
            placeholder.setCheckState(Qt.CheckState.Checked)
            self._list.addItem(placeholder)
            return

        for group_id in sorted(desired):
            label = self._wizard.group_label(group_id)
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, group_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            state = Qt.CheckState.Checked if not selected or group_id in selected else Qt.CheckState.Unchecked
            item.setCheckState(state)
            self._list.addItem(item)

    def _handle_select_all(self) -> None:
        for index in range(self._list.count()):
            item = self._list.item(index)
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                item.setCheckState(Qt.CheckState.Checked)

    def _handle_select_staged(self) -> None:
        staged_ids = self._wizard.staged_group_ids()
        for index in range(self._list.count()):
            item = self._list.item(index)
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                group_id = item.data(Qt.ItemDataRole.UserRole)
                state = Qt.CheckState.Checked if group_id in staged_ids else Qt.CheckState.Unchecked
                item.setCheckState(state)


class _ConfigureSettingsPage(QWizardPage):
    def __init__(self, wizard: BulkAssignmentWizard) -> None:
        super().__init__(wizard)
        self._wizard = wizard
        self.setTitle("Step 3 — Configure options & resolve conflicts")
        self.setSubTitle("Adjust bulk apply settings and choose how to handle updates to existing assignments.")

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        options_group = QGroupBox("Apply options")
        options_layout = QFormLayout(options_group)
        self._notify_checkbox = QCheckBox("Send notifications to end users (where supported)")
        self._skip_warnings_checkbox = QCheckBox("Allow apply even if warnings are detected")
        self._retry_checkbox = QCheckBox("Automatically retry transient conflicts")
        options_layout.addRow(self._notify_checkbox)
        options_layout.addRow(self._skip_warnings_checkbox)
        options_layout.addRow(self._retry_checkbox)
        layout.addWidget(options_group)

        conflict_group = QGroupBox("Conflict resolution")
        conflict_layout = QVBoxLayout(conflict_group)
        self._conflict_container = QWidget()
        self._conflict_container_layout = QVBoxLayout(self._conflict_container)
        self._conflict_container_layout.setContentsMargins(0, 0, 0, 0)
        self._conflict_container_layout.setSpacing(8)
        conflict_layout.addWidget(_ScrollContainer(self._conflict_container))
        self._conflict_placeholder = QLabel("No conflicts detected. Desired assignments will be applied as-is.")
        self._conflict_placeholder.setStyleSheet("color: palette(mid);")
        conflict_layout.addWidget(self._conflict_placeholder)
        layout.addWidget(conflict_group, stretch=1)

        layout.addStretch()
        self.setLayout(layout)

        self._conflict_rows: List[_ConflictRow] = []

        self._notify_checkbox.toggled.connect(self._handle_notify_changed)
        self._skip_warnings_checkbox.toggled.connect(self._handle_skip_warnings_changed)
        self._retry_checkbox.toggled.connect(self._handle_retry_changed)

    def initializePage(self) -> None:
        options = self._wizard.options()
        self._notify_checkbox.setChecked(options.notify_end_users)
        self._skip_warnings_checkbox.setChecked(options.skip_warnings)
        self._retry_checkbox.setChecked(options.retry_conflicts)
        self._populate_conflicts()

    def validatePage(self) -> bool:
        self._store_conflict_choices()
        return True

    def invalidate_conflicts(self) -> None:
        if self.isVisible():
            self._populate_conflicts()

    def _populate_conflicts(self) -> None:
        while self._conflict_container_layout.count():
            item = self._conflict_container_layout.takeAt(0)
            if widget := item.widget():
                widget.setParent(None)
        self._conflict_rows.clear()

        descriptors = self._wizard.conflict_descriptors()
        if not descriptors:
            self._conflict_placeholder.show()
            return

        self._conflict_placeholder.hide()
        for descriptor in descriptors:
            default_choice = self._wizard.conflict_choice(
                descriptor.app_id,
                descriptor.update.current.id,
            )
            row = _ConflictRow(descriptor, default_apply=default_choice)
            self._conflict_container_layout.addWidget(row)
            self._conflict_rows.append(row)
        self._conflict_container_layout.addStretch()

    def _store_conflict_choices(self) -> None:
        for row in self._conflict_rows:
            self._wizard.set_conflict_choice(
                row.descriptor.app_id,
                row.descriptor.update.current.id,
                row.apply,
            )

    def _handle_notify_changed(self, checked: bool) -> None:
        self._wizard.set_options(notify_end_users=checked)

    def _handle_skip_warnings_changed(self, checked: bool) -> None:
        self._wizard.set_options(skip_warnings=checked)

    def _handle_retry_changed(self, checked: bool) -> None:
        self._wizard.set_options(retry_conflicts=checked)


class _PreviewPage(QWizardPage):
    def __init__(self, wizard: BulkAssignmentWizard) -> None:
        super().__init__(wizard)
        self._wizard = wizard
        self.setTitle("Step 4 — Preview changes")
        self.setSubTitle("Review the operations that will run before applying.")

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        summary_group = QGroupBox("Summary")
        summary_layout = QVBoxLayout(summary_group)
        self._summary_view = QTableView()
        self._summary_view.setModel(self._wizard.summary_model())
        self._summary_view.setSelectionMode(QTableView.SelectionMode.NoSelection)
        self._summary_view.verticalHeader().setVisible(False)
        self._summary_view.horizontalHeader().setStretchLastSection(True)
        summary_layout.addWidget(self._summary_view)
        layout.addWidget(summary_group, stretch=2)

        detail_group = QGroupBox("Detailed operations")
        detail_layout = QVBoxLayout(detail_group)
        self._detail_view = QTableView()
        self._detail_view.setModel(self._wizard.detail_model())
        self._detail_view.setSelectionMode(QTableView.SelectionMode.NoSelection)
        self._detail_view.verticalHeader().setVisible(False)
        self._detail_view.horizontalHeader().setStretchLastSection(True)
        detail_layout.addWidget(self._detail_view)
        layout.addWidget(detail_group, stretch=2)

        warnings_group = QGroupBox("Warnings")
        warnings_layout = QVBoxLayout(warnings_group)
        self._warnings_label = QLabel()
        self._warnings_label.setWordWrap(True)
        warnings_layout.addWidget(self._warnings_label)
        layout.addWidget(warnings_group)

        helper = QLabel(
            "Select Finish to begin applying the assignments. A cancellable progress dialog will track execution.",
        )
        helper.setWordWrap(True)
        helper.setStyleSheet("color: palette(mid);")
        layout.addWidget(helper)

        self.setLayout(layout)

    def initializePage(self) -> None:
        self._wizard.rebuild_preview()
        warnings = self._wizard.preview_warnings()
        if warnings:
            self._warnings_label.setText("\n".join(warnings))
            self._warnings_label.setStyleSheet("color: palette(warning);")
        else:
            self._warnings_label.setText("No warnings detected.")
            self._warnings_label.setStyleSheet("color: palette(mid);")

    def isFinalPage(self) -> bool:
        return True

    def validatePage(self) -> bool:
        self._wizard.rebuild_preview()
        return bool(self._wizard.filtered_diffs())


__all__ = ["BulkAssignmentPlan", "BulkAssignmentWizard", "BulkWizardOptions"]
