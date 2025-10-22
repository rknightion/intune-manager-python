from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QSplitter,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from intune_manager.data import AssignmentFilter, DirectoryGroup, MobileApp, MobileAppAssignment
from intune_manager.services.assignments import AssignmentAppliedEvent, AssignmentDiff
from intune_manager.services.base import ServiceErrorEvent
from intune_manager.services import ServiceRegistry
from intune_manager.ui.components import (
    CommandAction,
    PageScaffold,
    ToastLevel,
    UIContext,
    consume_groups,
    make_toolbar_button,
)
from intune_manager.utils import get_logger

from .controller import AssignmentCenterController
from .models import (
    AssignmentTableModel,
    DiffDetailModel,
    DiffSummary,
    DiffSummaryModel,
    DiffDetail,
)


logger = get_logger(__name__)


def _clone_for_desired(assignments: Iterable[MobileAppAssignment]) -> list[MobileAppAssignment]:
    cloned: list[MobileAppAssignment] = []
    for assignment in assignments:
        cloned.append(assignment.model_copy(update={"id": None}))
    return cloned


class AssignmentsWidget(PageScaffold):
    """Assignment centre workspace for bulk comparison and apply flows."""

    def __init__(
        self,
        services: ServiceRegistry,
        *,
        context: UIContext,
        parent: QWidget | None = None,
    ) -> None:
        self._services = services
        self._context = context
        self._controller = AssignmentCenterController(services)

        self._preview_button = make_toolbar_button(
            "Dry-run preview",
            tooltip="Compare desired assignments against selected target apps without applying changes.",
        )
        self._apply_button = make_toolbar_button(
            "Apply changes",
            tooltip="Apply the computed assignment diff to selected target applications.",
        )
        self._backup_button = make_toolbar_button(
            "Export backup",
            tooltip="Export the desired assignment payload to JSON for backup or auditing.",
        )
        self._restore_button = make_toolbar_button(
            "Import assignments",
            tooltip="Import assignments from a JSON export to use as the desired state.",
        )

        actions: List[QToolButton] = [
            self._preview_button,
            self._apply_button,
            self._backup_button,
            self._restore_button,
        ]

        super().__init__(
            "Assignments",
            subtitle="Review, back up, and orchestrate application assignment changes with clear diffs and warnings.",
            actions=actions,
            parent=parent,
        )

        self._apps: list[MobileApp] = []
        self._app_index: Dict[str, MobileApp] = {}
        self._group_lookup: Dict[str, DirectoryGroup] = {}
        self._filter_lookup: Dict[str, AssignmentFilter] = {}
        self._assignment_cache: Dict[str, list[MobileAppAssignment]] = {}
        self._source_assignments: list[MobileAppAssignment] = []
        self._desired_assignments: list[MobileAppAssignment] = []
        self._desired_origin: str = "cache"
        self._diff_cache: Dict[str, AssignmentDiff] = {}
        self._source_app_id: str | None = None
        self._history_limit = 200

        self._search_input: QLineEdit | None = None
        self._source_list: QListWidget | None = None
        self._target_list: QListWidget | None = None
        self._assignment_table = AssignmentTableModel()
        self._diff_summary_model = DiffSummaryModel()
        self._diff_detail_model = DiffDetailModel()
        self._assignment_view: QTableView | None = None
        self._summary_view: QTableView | None = None
        self._detail_view: QTableView | None = None
        self._warnings_list: QListWidget | None = None
        self._history_list: QListWidget | None = None
        self._assignment_status_label: QLabel | None = None
        self._dry_run_checkbox: QCheckBox | None = None
        self._command_unregisters: list[Callable[[], None]] = []
        self._staged_groups: dict[str, str] = {}

        self._build_body()
        self._refresh_staged_groups_summary()
        self._wire_events()
        self._load_initial_data()

        self.destroyed.connect(lambda *_: self._on_destroyed())

    # ------------------------------------------------------------------ Setup

    def _build_body(self) -> None:
        self._build_filters()
        self._build_main_splitter()

    def _build_filters(self) -> None:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 12)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search applications…")
        layout.addWidget(self._search_input, stretch=2)

        self._dry_run_checkbox = QCheckBox("Dry-run only")
        self._dry_run_checkbox.setChecked(True)
        layout.addWidget(self._dry_run_checkbox)

        self.body_layout.addWidget(row)

    def _build_main_splitter(self) -> None:
        main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.setChildrenCollapsible(False)

        top_split = QSplitter(Qt.Orientation.Horizontal)
        top_split.setChildrenCollapsible(False)

        top_split.addWidget(self._build_source_panel())
        top_split.addWidget(self._build_review_panel())
        top_split.setStretchFactor(0, 1)
        top_split.setStretchFactor(1, 2)

        main_splitter.addWidget(top_split)
        main_splitter.addWidget(self._build_history_panel())
        main_splitter.setStretchFactor(0, 4)
        main_splitter.setStretchFactor(1, 1)

        self.body_layout.addWidget(main_splitter, stretch=1)

    def _build_source_panel(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        source_box = QGroupBox("Source application")
        source_layout = QVBoxLayout(source_box)
        self._source_list = QListWidget()
        self._source_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._source_list.setAlternatingRowColors(True)
        source_layout.addWidget(self._source_list)
        layout.addWidget(source_box, stretch=3)

        target_box = QGroupBox("Target applications")
        target_layout = QVBoxLayout(target_box)
        self._target_list = QListWidget()
        self._target_list.setAlternatingRowColors(True)
        self._target_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        target_layout.addWidget(self._target_list, stretch=1)

        actions_row = QHBoxLayout()
        select_all = QToolButton()
        select_all.setText("Select all")
        select_all.clicked.connect(self._select_all_targets)
        clear_all = QToolButton()
        clear_all.setText("Clear")
        clear_all.clicked.connect(self._clear_targets)
        actions_row.addWidget(select_all)
        actions_row.addWidget(clear_all)
        actions_row.addStretch()
        target_layout.addLayout(actions_row)
        layout.addWidget(target_box, stretch=4)

        info_box = QGroupBox("Using the assignment centre")
        info_layout = QFormLayout(info_box)
        info_layout.addRow("1.",
                           QLabel("Pick a source app. Its assignments become the desired state by default."))
        info_layout.addRow("2.",
                           QLabel("Select one or more target apps to preview differences."))
        info_layout.addRow("3.",
                           QLabel("Use dry-run preview to review changes, then apply when ready."))
        layout.addWidget(info_box)

        return container

    def _build_review_panel(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        assignment_group = QGroupBox("Desired assignments")
        assignment_layout = QVBoxLayout(assignment_group)

        self._assignment_status_label = QLabel("No source selected.")
        self._assignment_status_label.setStyleSheet("color: palette(mid);")
        assignment_layout.addWidget(self._assignment_status_label)

        self._assignment_view = QTableView()
        self._assignment_view.setModel(self._assignment_table)
        self._assignment_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._assignment_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._assignment_view.setAlternatingRowColors(True)
        self._assignment_view.verticalHeader().setVisible(False)
        self._assignment_view.horizontalHeader().setStretchLastSection(True)
        assignment_layout.addWidget(self._assignment_view, stretch=1)

        layout.addWidget(assignment_group, stretch=3)

        diff_group = QGroupBox("Dry-run preview")
        diff_layout = QVBoxLayout(diff_group)
        self._summary_view = QTableView()
        self._summary_view.setModel(self._diff_summary_model)
        self._summary_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._summary_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._summary_view.setAlternatingRowColors(True)
        self._summary_view.verticalHeader().setVisible(False)
        self._summary_view.horizontalHeader().setStretchLastSection(True)
        diff_layout.addWidget(self._summary_view, stretch=1)

        self._detail_view = QTableView()
        self._detail_view.setModel(self._diff_detail_model)
        self._detail_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._detail_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._detail_view.setAlternatingRowColors(True)
        self._detail_view.verticalHeader().setVisible(False)
        self._detail_view.horizontalHeader().setStretchLastSection(True)
        diff_layout.addWidget(self._detail_view, stretch=1)

        staged_box = QGroupBox("Staged target groups")
        staged_layout = QVBoxLayout(staged_box)
        staged_layout.setContentsMargins(8, 8, 8, 8)
        self._staged_groups_list = QListWidget()
        self._staged_groups_list.setAlternatingRowColors(True)
        self._staged_groups_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        staged_layout.addWidget(self._staged_groups_list)
        diff_layout.addWidget(staged_box)

        warnings_box = QGroupBox("Warnings & notes")
        warnings_layout = QVBoxLayout(warnings_box)
        self._warnings_list = QListWidget()
        self._warnings_list.setAlternatingRowColors(True)
        warnings_layout.addWidget(self._warnings_list)
        diff_layout.addWidget(warnings_box)

        layout.addWidget(diff_group, stretch=4)
        return container

    def _build_history_panel(self) -> QWidget:
        container = QGroupBox("History")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 8, 12, 8)

        self._history_list = QListWidget()
        self._history_list.setAlternatingRowColors(True)
        self._history_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self._history_list)
        return container

    def _wire_events(self) -> None:
        if self._search_input is not None:
            self._search_input.textChanged.connect(self._populate_app_lists)
        if self._source_list is not None:
            self._source_list.currentItemChanged.connect(self._handle_source_changed)
        if self._target_list is not None:
            self._target_list.itemChanged.connect(lambda *_: self._update_toolbar_state())

        self._preview_button.clicked.connect(self._handle_preview_clicked)
        self._apply_button.clicked.connect(self._handle_apply_clicked)
        self._backup_button.clicked.connect(self._handle_backup_clicked)
        self._restore_button.clicked.connect(self._handle_restore_clicked)

        if self._summary_view is not None:
            selection = self._summary_view.selectionModel()
            if selection is not None:
                selection.selectionChanged.connect(lambda *_: self._handle_summary_selection())

        if self._dry_run_checkbox is not None:
            self._dry_run_checkbox.toggled.connect(lambda *_: self._update_toolbar_state())

        self._command_unregisters.append(
            self._context.command_registry.register(
                CommandAction(
                    id="assignments.preview",
                    title="Assignments: Dry-run preview",
                    callback=self._handle_preview_clicked,
                    category="Assignments",
                    shortcut="Ctrl+Shift+A",
                ),
            ),
        )
        self._command_unregisters.append(
            self._context.command_registry.register(
                CommandAction(
                    id="assignments.consume-staged-groups",
                    title="Assignments: Use staged groups",
                    callback=self._consume_staged_groups_command,
                    category="Assignments",
                    description="Import staged group targets from the Groups module.",
                ),
            ),
        )

        self._controller.register_callbacks(
            applied=self._handle_assignment_applied,
            error=self._handle_service_error,
        )

    # ----------------------------------------------------------------- Data

    def _load_initial_data(self) -> None:
        apps = sorted(self._controller.list_apps(), key=lambda app: (app.display_name or "").lower())
        self._apps = apps
        self._app_index = {app.id: app for app in apps if app.id}
        self._populate_app_lists()

        self._group_lookup = {group.id: group for group in self._controller.list_groups() if group.id}
        self._filter_lookup = {flt.id: flt for flt in self._controller.list_filters() if flt.id}

        if not self._controller.is_assignment_service_available():
            self._context.show_banner(
                "Assignment service not configured — enable Microsoft Graph Intune assignments to unlock this module.",
                level=ToastLevel.WARNING,
            )
            self._apply_button.setEnabled(False)
            self._backup_button.setEnabled(False)
        else:
            self._apply_button.setEnabled(False)
            self._backup_button.setEnabled(True)

        self._preview_button.setEnabled(bool(apps))
        if not apps:
            self._assignment_status_label.setText("No applications cached. Refresh application data first.")

        self._refresh_staged_groups_summary()

    def _populate_app_lists(self) -> None:
        if self._source_list is None or self._target_list is None:
            return
        search = (self._search_input.text() if self._search_input else "").strip().lower()
        current_source = self._source_app_id
        checked_targets = {
            self._target_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._target_list.count())
            if self._target_list.item(i).checkState() == Qt.CheckState.Checked
        }
        self._source_list.blockSignals(True)
        self._target_list.blockSignals(True)
        self._source_list.clear()
        self._target_list.clear()
        for app in self._apps:
            label = app.display_name or "(Unnamed)"
            if search and search not in label.lower():
                continue
            source_item = QListWidgetItem(label)
            source_item.setData(Qt.ItemDataRole.UserRole, app.id)
            self._source_list.addItem(source_item)
            if app.id == current_source:
                source_item.setSelected(True)

            target_item = QListWidgetItem(label)
            target_item.setData(Qt.ItemDataRole.UserRole, app.id)
            target_item.setFlags(target_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            target_item.setCheckState(Qt.CheckState.Checked if app.id in checked_targets else Qt.CheckState.Unchecked)
            self._target_list.addItem(target_item)
        self._source_list.blockSignals(False)
        self._target_list.blockSignals(False)
        self._update_toolbar_state()

    # ----------------------------------------------------------------- Handlers

    def _handle_source_changed(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,  # noqa: ARG002
    ) -> None:
        if current is None:
            self._source_app_id = None
            self._assignment_status_label.setText("Select a source application to begin.")
            self._assignment_table.set_assignments(
                [],
                group_lookup=self._group_lookup,
                filter_lookup=self._filter_lookup,
            )
            return
        app_id = current.data(Qt.ItemDataRole.UserRole)
        if not app_id:
            return
        self._source_app_id = app_id
        self._desired_origin = "cache"
        self._diff_cache.clear()
        self._diff_summary_model.set_summaries([])
        self._diff_detail_model.set_details([])
        self._clear_warnings()

        self._context.set_busy("Loading source assignments…")
        self._context.run_async(self._load_source_assignments(app_id))

    async def _load_source_assignments(self, app_id: str) -> None:
        try:
            assignments = await self._get_assignments(app_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to load assignments", app_id=app_id)
            self._context.clear_busy()
            self._context.show_notification(f"Unable to load assignments: {exc}", level=ToastLevel.ERROR)
            return

        self._source_assignments = assignments
        self._desired_assignments = _clone_for_desired(assignments)
        app_name = self._app_index.get(app_id).display_name if app_id in self._app_index else app_id
        self._assignment_table.set_assignments(
            self._desired_assignments,
            group_lookup=self._group_lookup,
            filter_lookup=self._filter_lookup,
        )
        self._assignment_status_label.setText(
            f"{len(assignments):,} assignments loaded from {app_name}.",
        )
        self._refresh_staged_groups_summary()
        self._append_history(f"Loaded assignments for {app_name}")
        self._context.clear_busy()
        self._update_toolbar_state()

    async def _get_assignments(self, app_id: str) -> list[MobileAppAssignment]:
        if app_id in self._assignment_cache:
            return list(self._assignment_cache[app_id])
        app = self._app_index.get(app_id)
        if app and app.assignments:
            assignments = list(app.assignments)
        else:
            assignments = await self._controller.fetch_assignments(app_id)
        self._assignment_cache[app_id] = assignments
        return list(assignments)

    def _handle_preview_clicked(self) -> None:
        target_ids = self._selected_target_ids()
        if not target_ids:
            self._context.show_notification(
                "Select at least one target application to preview changes.",
                level=ToastLevel.WARNING,
            )
            return
        if not self._desired_assignments:
            self._context.show_notification(
                "Load or import desired assignments before running a preview.",
                level=ToastLevel.WARNING,
            )
            return
        self._context.set_busy("Calculating assignment diffs…")
        self._context.run_async(self._preview_async(target_ids))

    async def _preview_async(self, target_ids: list[str]) -> None:
        summaries: list[DiffSummary] = []
        warnings: list[str] = []
        new_diff_cache: dict[str, AssignmentDiff] = {}
        desired_payload = list(self._desired_assignments)

        for target_id in target_ids:
            try:
                current_assignments = await self._get_assignments(target_id)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to load target assignments", target_id=target_id)
                self._context.show_notification(
                    f"Unable to load assignments for target {target_id}: {exc}",
                    level=ToastLevel.ERROR,
                )
                continue

            diff = self._controller.diff_assignments(
                current=current_assignments,
                desired=desired_payload,
            )
            if diff is None:
                self._context.show_notification(
                    "Assignment service unavailable; cannot compute diff.",
                    level=ToastLevel.ERROR,
                )
                break

            app_name = self._app_index.get(target_id).display_name if target_id in self._app_index else target_id
            summary_warnings = self._collect_warnings(target_id, diff)
            summaries.append(
                DiffSummary(
                    app_id=target_id,
                    app_name=app_name or target_id,
                    creates=len(diff.to_create),
                    updates=len(diff.to_update),
                    deletes=len(diff.to_delete),
                    warnings=summary_warnings,
                    has_filters=any(
                        getattr(item.target, "assignment_filter_id", None)
                        for item in diff.to_create + [update.desired for update in diff.to_update]
                    ),
                ),
            )
            warnings.extend(f"{app_name}: {warning}" for warning in summary_warnings)
            new_diff_cache[target_id] = diff

        self._diff_cache = new_diff_cache
        self._diff_summary_model.set_summaries(summaries)
        if summaries:
            self._select_first_summary_row()
        else:
            self._diff_detail_model.set_details([])
        self._populate_warnings(warnings)
        self._context.clear_busy()
        self._append_history(
            f"Preview complete for {len(summaries)} target(s)",
            warning=bool(warnings),
        )
        self._update_toolbar_state()

    def _handle_apply_clicked(self) -> None:
        if self._dry_run_checkbox is not None and self._dry_run_checkbox.isChecked():
            self._context.show_notification(
                "Dry-run mode is enabled — disable it to apply assignments.",
                level=ToastLevel.INFO,
            )
            return
        if not self._diff_cache:
            self._context.show_notification(
                "Run a dry-run preview before applying assignments.",
                level=ToastLevel.WARNING,
            )
            return

        pending = {app_id: diff for app_id, diff in self._diff_cache.items() if not diff.is_noop}
        if not pending:
            self._context.show_notification(
                "No changes detected for selected targets.",
                level=ToastLevel.INFO,
            )
            return

        button = QMessageBox.question(
            self,
            "Apply assignment changes",
            "Apply the computed assignment changes to the selected targets?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if button != QMessageBox.StandardButton.Yes:
            return

        self._context.set_busy("Applying assignment changes…")
        self._context.run_async(self._apply_async(pending))

    async def _apply_async(self, pending: Dict[str, AssignmentDiff]) -> None:
        successes = 0
        failures = 0
        for app_id, diff in pending.items():
            app_name = self._app_index.get(app_id).display_name if app_id in self._app_index else app_id
            try:
                await self._controller.apply_diff(app_id, diff)
                self._append_history(
                    f"Applied assignments to {app_name}: +{len(diff.to_create)}/~{len(diff.to_update)}/-{len(diff.to_delete)}",
                )
                successes += 1
                # Refresh cache so subsequent previews reflect new state.
                self._assignment_cache[app_id] = await self._controller.fetch_assignments(app_id)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to apply assignment diff", app_id=app_id)
                self._append_history(
                    f"Failed to apply assignments to {app_name}: {exc}",
                    warning=True,
                )
                failures += 1
        self._context.clear_busy()
        if failures:
            self._context.show_notification(
                f"Assignments applied with {failures} failure(s). Check history for details.",
                level=ToastLevel.WARNING,
            )
        else:
            self._context.show_notification(
                f"Assignments applied to {successes} target(s).",
                level=ToastLevel.SUCCESS,
            )
        self._diff_cache.clear()
        self._diff_summary_model.set_summaries([])
        self._diff_detail_model.set_details([])
        self._clear_warnings()
        self._update_toolbar_state()

    def _handle_backup_clicked(self) -> None:
        if not self._desired_assignments:
            self._context.show_notification(
                "No desired assignments available to export.",
                level=ToastLevel.WARNING,
            )
            return
        try:
            payload = self._controller.export_assignments(self._desired_assignments)
        except Exception as exc:  # noqa: BLE001
            self._context.show_notification(
                f"Unable to export assignments: {exc}",
                level=ToastLevel.ERROR,
            )
            return
        suggested = f"assignments-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export assignments",
            suggested,
            "JSON files (*.json);;All files (*)",
        )
        if not path:
            return
        try:
            with Path(path).open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to write export file", path=path)
            self._context.show_notification(
                f"Failed to write file: {exc}",
                level=ToastLevel.ERROR,
            )
            return
        self._append_history(f"Exported assignments to {path}")
        self._context.show_notification("Assignments exported successfully.", level=ToastLevel.SUCCESS)

    def _handle_restore_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import assignments",
            "",
            "JSON files (*.json);;All files (*)",
        )
        if not path:
            return
        try:
            with Path(path).open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception as exc:  # noqa: BLE001
            self._context.show_notification(
                f"Failed to read file: {exc}",
                level=ToastLevel.ERROR,
            )
            return
        if not isinstance(payload, list):
            self._context.show_notification(
                "Import expected a JSON array of assignments.",
                level=ToastLevel.ERROR,
            )
            return
        try:
            assignments = [MobileAppAssignment.from_graph(item) for item in payload]
        except Exception as exc:  # noqa: BLE001
            self._context.show_notification(
                f"JSON payload could not be parsed: {exc}",
                level=ToastLevel.ERROR,
            )
            return

        self._desired_assignments = _clone_for_desired(assignments)
        self._desired_origin = f"import:{Path(path).name}"
        self._assignment_table.set_assignments(
            self._desired_assignments,
            group_lookup=self._group_lookup,
            filter_lookup=self._filter_lookup,
        )
        self._assignment_status_label.setText(
            f"{len(self._desired_assignments):,} assignments loaded from import ({Path(path).name}).",
        )
        self._refresh_staged_groups_summary()
        self._append_history(f"Imported assignments from {path}")
        self._diff_cache.clear()
        self._diff_summary_model.set_summaries([])
        self._diff_detail_model.set_details([])
        self._clear_warnings()
        self._update_toolbar_state()

    def _handle_summary_selection(self) -> None:
        if self._summary_view is None:
            return
        selection = self._summary_view.selectionModel()
        if selection is None:
            return
        indexes = selection.selectedRows()
        if not indexes:
            return
        row = indexes[0].row()
        summary = self._diff_summary_model.summary_at(row)
        if summary is None:
            return
        diff = self._diff_cache.get(summary.app_id)
        if diff is None:
            return
        details = DiffDetailModel.from_diff(
            diff,
            groups=self._group_lookup,
            filters=self._filter_lookup,
        )
        self._diff_detail_model.set_details(details)

    def _handle_assignment_applied(self, event: AssignmentAppliedEvent) -> None:
        app_name = self._app_index.get(event.app_id).display_name if event.app_id in self._app_index else event.app_id
        self._append_history(
            f"Assignments applied for {app_name}: +{len(event.diff.to_create)}/~{len(event.diff.to_update)}/-{len(event.diff.to_delete)}",
        )

    def _handle_service_error(self, event: ServiceErrorEvent) -> None:
        detail = str(event.error)
        self._append_history(f"Assignment service error: {detail}", warning=True)
        self._context.show_notification(
            f"Assignment operation failed: {detail}",
            level=ToastLevel.ERROR,
        )

    # ----------------------------------------------------------------- Helpers

    def _consume_staged_groups_command(self) -> None:
        buffer = consume_groups()
        if not buffer.entries:
            self._context.show_notification(
                "No staged groups available.",
                level=ToastLevel.INFO,
            )
            return
        self._apply_staged_groups(buffer.entries)

    def _apply_staged_groups(self, entries: Iterable[tuple[str, str]]) -> None:
        staged = {group_id: name for group_id, name in entries if group_id}
        if not staged:
            self._staged_groups.clear()
            self._refresh_staged_groups_summary()
            self._context.show_notification("Cleared staged groups.", level=ToastLevel.INFO)
            return
        self._staged_groups = staged
        self._refresh_staged_groups_summary()
        self._append_history(
            f"Imported {len(staged)} staged group(s): {', '.join(staged.values())}",
        )
        self._context.show_notification(
            f"Imported {len(staged)} staged group(s) from Groups.",
            level=ToastLevel.SUCCESS,
        )

    def _refresh_staged_groups_summary(self) -> None:
        if self._staged_groups_list is None:
            return
        self._staged_groups_list.clear()
        if not self._staged_groups:
            placeholder = QListWidgetItem("No staged groups.")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._staged_groups_list.addItem(placeholder)
            return
        for group_id, name in self._staged_groups.items():
            covered = self._assignment_contains_group(group_id)
            status = "included" if covered else "missing"
            item = QListWidgetItem(f"{name} — {status}")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            item.setForeground(Qt.GlobalColor.darkGreen if covered else Qt.GlobalColor.darkYellow)
            self._staged_groups_list.addItem(item)

    def _assignment_contains_group(self, group_id: str) -> bool:
        return any(
            getattr(assignment.target, "group_id", None) == group_id
            for assignment in self._desired_assignments
        )

    def _collect_warnings(self, target_id: str, diff: AssignmentDiff) -> list[str]:
        warnings: list[str] = []
        if target_id == self._source_app_id:
            warnings.append("Target matches the source app; ensure this is intentional.")

        def inspect_assignment(assignment: MobileAppAssignment) -> None:
            group_id = getattr(assignment.target, "group_id", None)
            if group_id and group_id not in self._group_lookup:
                warnings.append(f"Group {group_id} not in cache.")
            filter_id = getattr(assignment.target, "assignment_filter_id", None)
            if filter_id and filter_id not in self._filter_lookup:
                warnings.append(f"Filter {filter_id} not in cache.")

        for assignment in diff.to_create:
            inspect_assignment(assignment)
        for update in diff.to_update:
            inspect_assignment(update.desired)
        for assignment in diff.to_delete:
            inspect_assignment(assignment)
        if diff.is_noop:
            warnings.append("No changes detected.")
        return warnings

    def _populate_warnings(self, warnings: list[str]) -> None:
        if self._warnings_list is None:
            return
        self._warnings_list.clear()
        if not warnings:
            self._warnings_list.addItem("No warnings detected.")
            return
        for warning in warnings:
            item = QListWidgetItem(warning)
            item.setForeground(Qt.GlobalColor.darkYellow)
            self._warnings_list.addItem(item)

    def _clear_warnings(self) -> None:
        if self._warnings_list is not None:
            self._warnings_list.clear()
            self._warnings_list.addItem("No warnings yet.")

    def _append_history(self, message: str, *, warning: bool = False) -> None:
        if self._history_list is None:
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = QListWidgetItem(f"[{timestamp}] {message}")
        if warning:
            entry.setForeground(Qt.GlobalColor.darkYellow)
        self._history_list.addItem(entry)
        while self._history_list.count() > self._history_limit:
            item = self._history_list.takeItem(0)
            del item
        self._history_list.scrollToBottom()

    def _select_first_summary_row(self) -> None:
        if self._summary_view is None:
            return
        if self._diff_summary_model.rowCount() == 0:
            return
        self._summary_view.selectRow(0)
        self._handle_summary_selection()

    def _selected_target_ids(self) -> list[str]:
        if self._target_list is None:
            return []
        ids: list[str] = []
        for index in range(self._target_list.count()):
            item = self._target_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                app_id = item.data(Qt.ItemDataRole.UserRole)
                if app_id:
                    ids.append(app_id)
        return ids

    def _select_all_targets(self) -> None:
        if self._target_list is None:
            return
        for index in range(self._target_list.count()):
            item = self._target_list.item(index)
            item.setCheckState(Qt.CheckState.Checked)
        self._update_toolbar_state()

    def _clear_targets(self) -> None:
        if self._target_list is None:
            return
        for index in range(self._target_list.count()):
            item = self._target_list.item(index)
            item.setCheckState(Qt.CheckState.Unchecked)
        self._update_toolbar_state()

    def _update_toolbar_state(self) -> None:
        has_desired = bool(self._desired_assignments)
        targets_selected = bool(self._selected_target_ids())
        self._preview_button.setEnabled(has_desired and targets_selected)
        dry_run = self._dry_run_checkbox.isChecked() if self._dry_run_checkbox else True
        apply_enabled = (
            not dry_run
            and bool(self._diff_cache)
            and any(not diff.is_noop for diff in self._diff_cache.values())
            and self._controller.is_assignment_service_available()
        )
        self._apply_button.setEnabled(apply_enabled)
        self._backup_button.setEnabled(has_desired and self._controller.is_assignment_service_available())

    # ----------------------------------------------------------------- Cleanup

    def _cleanup(self) -> None:
        while self._command_unregisters:
            unregister = self._command_unregisters.pop()
            try:
                unregister()
            except Exception:  # pragma: no cover - defensive cleanup
                pass
        self._controller.dispose()

    def _on_destroyed(self) -> None:
        self._cleanup()


__all__ = ["AssignmentsWidget"]
