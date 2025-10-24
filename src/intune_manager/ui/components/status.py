from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .notifications import ToastLevel


_LEVEL_STYLES: dict[ToastLevel, dict[str, str]] = {
    ToastLevel.INFO: {
        "bg": "rgba(59, 130, 246, 0.14)",
        "accent": "rgba(59, 130, 246, 0.75)",
        "text": "#1d4ed8",
        "detail": "#1e293b",
    },
    ToastLevel.SUCCESS: {
        "bg": "rgba(34, 197, 94, 0.16)",
        "accent": "rgba(34, 197, 94, 0.75)",
        "text": "#15803d",
        "detail": "#14532d",
    },
    ToastLevel.WARNING: {
        "bg": "rgba(249, 115, 22, 0.16)",
        "accent": "rgba(249, 115, 22, 0.75)",
        "text": "#b45309",
        "detail": "#78350f",
    },
    ToastLevel.ERROR: {
        "bg": "rgba(239, 68, 68, 0.16)",
        "accent": "rgba(239, 68, 68, 0.8)",
        "text": "#b91c1c",
        "detail": "#7f1d1d",
    },
}


class InlineStatusMessage(QFrame):
    """Compact status banner suitable for inline placement within list views."""

    def __init__(
        self,
        *,
        parent: QWidget | None = None,
        closable: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("InlineStatusMessage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        self._message_label = QLabel()
        self._message_label.setObjectName("InlineStatusMessageText")
        self._message_label.setWordWrap(True)
        self._message_label.setTextFormat(Qt.TextFormat.PlainText)
        self._message_label.setStyleSheet("background: transparent;")
        self._message_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse,
        )
        header.addWidget(self._message_label, stretch=1)

        self._detail_toggle = QToolButton()
        self._detail_toggle.setText("Show details")
        self._detail_toggle.setCheckable(True)
        self._detail_toggle.setVisible(False)
        self._detail_toggle.toggled.connect(self._handle_detail_toggled)
        header.addWidget(self._detail_toggle)

        if closable:
            self._close_button: QToolButton | None = QToolButton()
            self._close_button.setAutoRaise(True)
            self._close_button.setText("×")
            self._close_button.clicked.connect(self.clear)
            header.addWidget(self._close_button)
        else:
            self._close_button = None

        layout.addLayout(header)

        self._detail_label = QLabel()
        self._detail_label.setObjectName("InlineStatusMessageDetail")
        self._detail_label.setWordWrap(True)
        self._detail_label.setTextFormat(Qt.TextFormat.PlainText)
        self._detail_label.setStyleSheet("background: transparent;")
        self._detail_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse,
        )
        detail_font = self._detail_label.font()
        detail_font.setPointSizeF(max(detail_font.pointSizeF() - 1.0, 8.0))
        self._detail_label.setFont(detail_font)
        self._detail_label.setVisible(False)
        layout.addWidget(self._detail_label)

        self.hide()

    # ------------------------------------------------------------------ Public API

    def display(
        self,
        message: str,
        *,
        level: ToastLevel = ToastLevel.INFO,
        detail: str | None = None,
    ) -> None:
        style = _LEVEL_STYLES.get(level, _LEVEL_STYLES[ToastLevel.INFO])
        self.setStyleSheet(
            "QFrame#InlineStatusMessage {"
            f"  background-color: {style['bg']};"
            f"  border-left: 4px solid {style['accent']};"
            "  border-radius: 12px;"
            "}"
            "QLabel#InlineStatusMessageText {"
            f"  color: {style['text']};"
            "  background: transparent;"
            "}"
            "QLabel#InlineStatusMessageDetail {"
            f"  color: {style['detail']};"
            "  background: transparent;"
            "  border-top: 1px solid rgba(15, 23, 42, 0.08);"
            "  margin-top: 6px;"
            "  padding-top: 6px;"
            "}"
        )
        self._message_label.setText(message)
        if detail:
            self._detail_label.setText(detail)
            self._detail_toggle.setVisible(True)
            # Reset toggle to collapsed view each time new detail arrives.
            if self._detail_toggle.isChecked():
                self._detail_toggle.setChecked(False)
            else:
                self._detail_label.setVisible(False)
                self._detail_toggle.setText("Show details")
        else:
            self._detail_toggle.setVisible(False)
            if self._detail_toggle.isChecked():
                self._detail_toggle.setChecked(False)
            self._detail_label.clear()
            self._detail_label.setVisible(False)
        self.show()

    def clear(self) -> None:
        self.hide()
        self._message_label.clear()
        self._detail_label.clear()
        self._detail_label.setVisible(False)
        if self._detail_toggle.isChecked():
            self._detail_toggle.blockSignals(True)
            self._detail_toggle.setChecked(False)
            self._detail_toggle.blockSignals(False)
        self._detail_toggle.setVisible(False)
        self._detail_toggle.setText("Show details")

    # ----------------------------------------------------------------- Handlers

    def _handle_detail_toggled(self, checked: bool) -> None:
        self._detail_label.setVisible(checked)
        self._detail_toggle.setText("Hide details" if checked else "Show details")


__all__ = ["InlineStatusMessage"]
