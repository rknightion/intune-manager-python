from __future__ import annotations

from typing import Dict

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QWidget,
)

from .notifications import ToastLevel


_LEVEL_STYLES: Dict[ToastLevel, dict[str, str]] = {
    ToastLevel.INFO: {
        "bg": "rgba(59, 130, 246, 0.15)",
        "border": "rgba(59, 130, 246, 0.45)",
        "text": "#1d4ed8",
    },
    ToastLevel.SUCCESS: {
        "bg": "rgba(34, 197, 94, 0.18)",
        "border": "rgba(34, 197, 94, 0.45)",
        "text": "#15803d",
    },
    ToastLevel.WARNING: {
        "bg": "rgba(249, 115, 22, 0.18)",
        "border": "rgba(249, 115, 22, 0.45)",
        "text": "#b45309",
    },
    ToastLevel.ERROR: {
        "bg": "rgba(239, 68, 68, 0.18)",
        "border": "rgba(239, 68, 68, 0.5)",
        "text": "#b91c1c",
    },
}


class AlertBanner(QFrame):
    """Notification banner displayed above primary content."""

    actionTriggered = Signal()
    dismissed = Signal()

    def __init__(
        self,
        *,
        parent: QWidget | None = None,
        closable: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("AlertBanner")
        self._action_button = QPushButton()
        self._closable = closable

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)

        self._message_label = QLabel()
        self._message_label.setWordWrap(True)
        self._message_label.setStyleSheet("background: transparent;")
        layout.addWidget(self._message_label, stretch=1)

        self._action_button.setVisible(False)
        self._action_button.clicked.connect(self.actionTriggered.emit)
        layout.addWidget(self._action_button)

        if closable:
            self._close_button = QToolButton()
            self._close_button.setText("×")
            self._close_button.setAutoRaise(True)
            self._close_button.clicked.connect(self._handle_close_clicked)
            layout.addWidget(self._close_button)
        else:
            self._close_button = None

        self.hide()

    # ----------------------------------------------------------------- Public API

    def display(
        self,
        message: str,
        *,
        level: ToastLevel = ToastLevel.INFO,
        action_label: str | None = None,
    ) -> None:
        style = _LEVEL_STYLES[level]
        self.setStyleSheet(
            "QFrame#AlertBanner {"
            f"  background-color: {style['bg']};"
            f"  border: 1px solid {style['border']};"
            "  border-radius: 10px;"
            "}"
            "QFrame#AlertBanner QLabel {"
            f"  color: {style['text']};"
            "  background: transparent;"
            "}"
        )
        self._message_label.setText(message)
        if action_label:
            self._action_button.setText(action_label)
            self._action_button.setVisible(True)
        else:
            self._action_button.setVisible(False)
        self.show()

    def clear(self) -> None:
        self.hide()
        self._message_label.clear()
        self._action_button.setVisible(False)

    # ----------------------------------------------------------------- Handlers

    def _handle_close_clicked(self) -> None:
        self.clear()
        self.dismissed.emit()


__all__ = ["AlertBanner"]
