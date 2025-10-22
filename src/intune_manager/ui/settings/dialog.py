from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from .controller import SettingsController
from .widgets import SettingsWidget


class SettingsDialog(QDialog):
    """Dialog wrapper that embeds the SettingsWidget."""

    def __init__(
        self,
        controller: SettingsController | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Intune Manager – Tenant Configuration")

        layout = QVBoxLayout(self)
        self.widget = SettingsWidget(controller=controller, parent=self)
        layout.addWidget(self.widget)

        buttons = QHBoxLayout()
        buttons.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)


__all__ = ["SettingsDialog"]
