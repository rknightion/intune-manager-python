from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from intune_manager.data import MobileAppAssignment
from intune_manager.services import AssignmentImportResult
from intune_manager.utils.sanitize import sanitize_log_message


class AssignmentImportDialog(QDialog):
    """Preview parsed assignment import rows with warnings and error log tooling."""

    def __init__(
        self,
        result: AssignmentImportResult,
        *,
        expected_app_name: str | None,
        expected_app_id: str | None,
        source_path: Path | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import assignments from CSV")
        self.resize(780, 520)

        self._result = result
        self._expected_app_name = expected_app_name or "selected application"
        self._expected_app_id = expected_app_id
        self._source_path = source_path
        self._accepted_assignments: list[MobileAppAssignment] = []

        self._summary_label: QLabel | None = None
        self._table: QTableWidget | None = None
        self._ok_button: QPushButton | None = None
        self._copy_button: QPushButton | None = None
        self._save_button: QPushButton | None = None

        self._build_ui()
        self._populate_table()
        self._update_summary()
        self._update_primary_state()

    def selected_assignments(self) -> list[MobileAppAssignment]:
        return list(self._accepted_assignments)

    # ------------------------------------------------------------------ UI build

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        summary = QLabel(parent=self)
        summary.setWordWrap(True)
        layout.addWidget(summary)
        self._summary_label = summary

        table = QTableWidget(0, 6, parent=self)
        table.setHorizontalHeaderLabels(
            ["Row", "Status", "App", "Group", "Intent", "Message"],
        )
        table.horizontalHeader().setStretchLastSection(True)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(table, stretch=1)
        self._table = table

        log_row = QHBoxLayout()
        copy_button = QPushButton("Copy log", parent=self)
        copy_button.clicked.connect(self._handle_copy_log)
        save_button = QPushButton("Save log…", parent=self)
        save_button.clicked.connect(self._handle_save_log)
        log_row.addWidget(copy_button)
        log_row.addWidget(save_button)
        log_row.addStretch()
        layout.addLayout(log_row)
        self._copy_button = copy_button
        self._save_button = save_button

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok,
            parent=self,
        )
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_button.setText("Use assignments")
        buttons.accepted.connect(self._handle_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._ok_button = ok_button

    def _populate_table(self) -> None:
        if self._table is None:
            return
        rows = self._result.rows
        self._table.setRowCount(len(rows))

        for index, row in enumerate(rows):
            status = row.status_label()
            message = ""
            if row.errors:
                message = "; ".join(row.errors)
            elif row.warnings:
                message = "; ".join(row.warnings)

            values = [
                str(row.row_number),
                status,
                row.app_name,
                row.group_name,
                row.intent_raw or "",
                message,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self._table.setItem(index, column, item)

            if row.errors:
                self._apply_row_brush(index, QColor("#fdecea"))
            elif row.warnings:
                self._apply_row_brush(index, QColor("#fff4e5"))

        self._table.resizeColumnsToContents()

    def _apply_row_brush(self, row_index: int, color: QColor) -> None:
        if self._table is None:
            return
        brush = QBrush(color)
        for column in range(self._table.columnCount()):
            item = self._table.item(row_index, column)
            if item is not None:
                item.setBackground(brush)

    def _update_summary(self) -> None:
        if self._summary_label is None:
            return
        total_rows = len(self._result.rows)
        error_count = len(self._result.errors)
        warning_count = len(self._result.warnings)
        assignments_count = sum(
            len(payload) for payload in self._result.assignments_by_app.values()
        )

        fragments: list[str] = [
            f"{assignments_count} assignment(s) parsed across {total_rows} row(s).",
        ]
        if warning_count:
            fragments.append(f"{warning_count} warning(s).")
        if error_count:
            fragments.append(f"{error_count} error(s) — fix before applying.")
        else:
            fragments.append("No blocking errors detected.")

        if self._expected_app_id:
            other_apps = [
                app_id
                for app_id in self._result.assignments_by_app.keys()
                if app_id != self._expected_app_id
            ]
            if other_apps:
                fragments.append(
                    f"{len(other_apps)} additional application(s) detected in file; only {self._expected_app_name} will be staged.",
                )

        if self._source_path is not None:
            fragments.append(f"Source file: {self._source_path.name}")

        self._summary_label.setText(" ".join(fragments))

    def _update_primary_state(self) -> None:
        if self._ok_button is None:
            return
        has_errors = self._result.has_fatal_errors()
        assignments_available = False
        if self._expected_app_id:
            assignments_available = bool(
                self._result.assignments_by_app.get(self._expected_app_id)
            )
        else:
            assignments_available = bool(self._result.assignments_by_app)
        self._ok_button.setEnabled(assignments_available and not has_errors)

        has_log = bool(self._result.warnings or self._result.errors)
        if self._copy_button is not None:
            self._copy_button.setEnabled(has_log)
        if self._save_button is not None:
            self._save_button.setEnabled(has_log)

    # ----------------------------------------------------------------- Actions

    def _handle_accept(self) -> None:
        if self._result.has_fatal_errors():
            QMessageBox.warning(
                self,
                "Import contains errors",
                "Resolve the highlighted errors in the CSV file before applying assignments.",
            )
            return
        if not self._expected_app_id:
            QMessageBox.warning(
                self,
                "No source application selected",
                (
                    "Select a source application in the assignment centre before importing. "
                    "The CSV rows will be applied as the desired assignments for that app."
                ),
            )
            return
        payload = self._result.assignments_by_app.get(self._expected_app_id)
        if not payload:
            available_apps = ", ".join(self._result.assignments_by_app.keys()) or "none"
            QMessageBox.warning(
                self,
                "No matching assignments",
                (
                    f"The CSV did not contain assignments for {self._expected_app_name}.\n"
                    f"Available application IDs in the file: {available_apps}"
                ),
            )
            return

        self._accepted_assignments = list(payload)
        self.accept()

    def _handle_copy_log(self) -> None:
        log_text = self._build_log_text()
        if not log_text:
            QMessageBox.information(
                self, "No log entries", "There are no warnings or errors to copy."
            )
            return
        QApplication.clipboard().setText(log_text)
        QMessageBox.information(
            self, "Log copied", "Warnings and errors copied to the clipboard."
        )

    def _handle_save_log(self) -> None:
        log_text = self._build_log_text()
        if not log_text:
            QMessageBox.information(
                self, "No log entries", "There are no warnings or errors to save."
            )
            return
        suggested_name = (
            f"{self._source_path.stem}-import-log.txt"
            if self._source_path is not None
            else "assignment-import-log.txt"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save import log",
            suggested_name,
            "Text files (*.txt);;All files (*)",
        )
        if not path:
            return
        try:
            Path(path).write_text(log_text, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self, "Failed to save log", f"Unable to save log: {exc}"
            )
            return
        QMessageBox.information(self, "Log saved", f"Import log saved to {path}.")

    # ----------------------------------------------------------------- Helpers

    def _build_log_text(self) -> str:
        lines: list[str] = []
        if self._result.warnings:
            lines.append("Warnings:")
            lines.extend(
                f"  - {sanitize_log_message(item)}" for item in self._result.warnings
            )
        if self._result.errors:
            if lines:
                lines.append("")
            lines.append("Errors:")
            lines.extend(
                f"  - {sanitize_log_message(item)}" for item in self._result.errors
            )
        return "\n".join(lines)


__all__ = ["AssignmentImportDialog"]
