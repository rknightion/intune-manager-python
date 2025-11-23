from __future__ import annotations

from PySide6.QtCore import Qt, QEvent, QObject, Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class BusyOverlay(QWidget):
    """Semi-transparent overlay that blocks input while a background task runs."""

    visibilityChanged = Signal(bool)

    def __init__(
        self,
        parent: QWidget,
        *,
        default_message: str = "Working…",
    ) -> None:
        super().__init__(parent)
        self._default_message = default_message
        self._message = default_message

        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setWindowFlags(Qt.WindowType.Widget | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("BusyOverlay")
        self.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("BusyOverlayContainer")
        container.setMinimumWidth(360)
        container.setMaximumWidth(520)
        container.setStyleSheet(
            "QFrame#BusyOverlayContainer {"
            "  background-color: rgba(15, 23, 42, 0.72);"
            "  border-radius: 16px;"
            "  padding: 24px;"
            "}"
            "QLabel#BusyOverlayMessage {"
            "  color: #f8fafc;"
            "  font-size: 16px;"
            "  font-weight: 500;"
            "}"
        )

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(24, 24, 24, 24)
        container_layout.setSpacing(12)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.setFixedHeight(6)
        progress.setTextVisible(False)
        progress.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        progress.setStyleSheet(
            "QProgressBar {"
            "  background-color: rgba(255, 255, 255, 0.24);"
            "  border-radius: 3px;"
            "}"
            "QProgressBar::chunk {"
            "  background-color: #38bdf8;"
            "  border-radius: 3px;"
            "}"
        )

        self._message_label = QLabel(self._message)
        self._message_label.setObjectName("BusyOverlayMessage")
        self._message_label.setWordWrap(True)
        self._message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        container_layout.addWidget(progress)
        container_layout.addWidget(self._message_label)

        layout.addStretch()
        layout.addWidget(container, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()

        parent.installEventFilter(self)

    # ------------------------------------------------------------------ Public

    def show_overlay(self, message: str | None = None) -> None:
        if message:
            self._message = message
        else:
            self._message = self._default_message
        self._message_label.setText(self._message)
        self._resize_to_parent()
        self.raise_()
        self.show()
        self.visibilityChanged.emit(True)

    def hide_overlay(self) -> None:
        if not self.isVisible():
            return
        self.hide()
        self.visibilityChanged.emit(False)

    def set_message(self, message: str) -> None:
        self._message = message
        self._message_label.setText(message)

    # ----------------------------------------------------------------- Overrides

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.parent():
            if event.type() in {
                QEvent.Type.Resize,
                QEvent.Type.Move,
                QEvent.Type.Show,
            }:
                self._resize_to_parent()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event: QEvent) -> None:  # type: ignore[override]
        self._resize_to_parent()
        super().resizeEvent(event)

    # ------------------------------------------------------------------ Helpers

    def _resize_to_parent(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.setGeometry(parent.rect())


__all__ = ["BusyOverlay"]
