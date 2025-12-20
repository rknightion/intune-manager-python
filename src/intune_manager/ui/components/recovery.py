from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


@dataclass(slots=True)
class CrashRecoveryDecision:
    safe_mode: bool
    purge_cache: bool


class CrashRecoveryDialog(QDialog):
    """Prompt shown when a previous session crashed."""

    def __init__(
        self,
        crash_info: dict[str, str],
        *,
        parent: QDialog | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Crash Recovery")
        self.setModal(True)
        self._crash_info = crash_info
        self._decision = CrashRecoveryDecision(False, False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        summary = self._format_summary(crash_info)
        label = QLabel(summary)
        label.setWordWrap(True)
        layout.addWidget(label)

        details = QTextEdit()
        details.setReadOnly(True)
        details.setText(self._format_details(crash_info))
        details.setMaximumHeight(160)
        layout.addWidget(details)

        self._safe_mode_box = QCheckBox("Launch in Safe Mode")
        self._safe_mode_box.setToolTip(
            "Safe Mode disables background refresh and diagnostics to help isolate issues."
        )
        layout.addWidget(self._safe_mode_box)

        self._purge_box = QCheckBox("Clear cached Graph data before launch")
        self._purge_box.setToolTip(
            "Removes cached devices, apps, groups, and attachments in case corrupted data caused the crash."
        )
        layout.addWidget(self._purge_box)

        open_button = QPushButton("Open crash log")
        open_button.clicked.connect(self._open_crash_report)
        layout.addWidget(open_button)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Continue launch")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Quit")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def decision(self) -> CrashRecoveryDecision:
        return CrashRecoveryDecision(
            safe_mode=self._safe_mode_box.isChecked(),
            purge_cache=self._purge_box.isChecked(),
        )

    def _open_crash_report(self) -> None:
        path = self._crash_info.get("report_path")
        if not path:
            return
        report = Path(path)
        if report.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(report)))

    def _format_summary(self, info: dict[str, str]) -> str:
        timestamp = info.get("timestamp")
        readable = timestamp
        if timestamp:
            try:
                readable = (
                    datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    .astimezone()
                    .strftime("%Y-%m-%d %H:%M:%S %Z")
                )
            except ValueError:
                readable = timestamp
        exception_type = info.get("exception_type", "Unknown exception")
        return (
            "Intune Manager did not exit cleanly during the previous session.\n"
            f"Crash detected at {readable} ({exception_type}). Choose how to continue."
        )

    def _format_details(self, info: dict[str, str]) -> str:
        try:
            return json.dumps(info, indent=2)
        except TypeError:
            return str(info)


__all__ = ["CrashRecoveryDialog", "CrashRecoveryDecision"]
