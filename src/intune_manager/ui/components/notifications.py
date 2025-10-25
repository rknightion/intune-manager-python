from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPropertyAnimation,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QCloseEvent, QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from .theme import ThemeManager


class ToastLevel(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


@dataclass(slots=True)
class ToastMessage:
    text: str
    level: ToastLevel = ToastLevel.INFO
    duration_ms: int = 4500


_LEVEL_COLORS = {
    ToastLevel.INFO: ("#2563eb", "#f8fafc"),
    ToastLevel.SUCCESS: ("#22c55e", "#042f14"),
    ToastLevel.WARNING: ("#f97316", "#0f172a"),
    ToastLevel.ERROR: ("#ef4444", "#fdf2f8"),
}


class ToastWidget(QFrame):
    closed = Signal()

    def __init__(self, message: ToastMessage, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._message = message
        bg, fg = _LEVEL_COLORS.get(message.level, _LEVEL_COLORS[ToastLevel.INFO])

        self.setObjectName("ToastWidget")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet(
            "QFrame#ToastWidget {"
            f"  background-color: {bg};"
            "  border-radius: 12px;"
            "  padding: 12px 16px;"
            "  color: white;"
            "}"
            "QPushButton#ToastDismiss {"
            "  background: transparent;"
            f"  color: {fg};"
            "  border: none;"
            "  font-weight: 600;"
            "}"
            "QPushButton#ToastDismiss:hover {"
            "  color: white;"
            "}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        self.label = QLabel(message.text)
        self.label.setWordWrap(True)
        self.label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self.label)

        self.dismiss_button = QPushButton("Dismiss")
        self.dismiss_button.setObjectName("ToastDismiss")
        self.dismiss_button.clicked.connect(self.close)
        layout.addWidget(self.dismiss_button)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(15, 23, 42, int(0.35 * 255)))
        shadow.setOffset(0, 10)
        self.setGraphicsEffect(shadow)

        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self._opacity_anim.setDuration(250)
        self._opacity_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._opacity_anim.finished.connect(self._handle_animation_finished)
        self._should_close = False

    def fade_in(self) -> None:
        self._should_close = False
        self.setWindowOpacity(0.0)
        self._opacity_anim.stop()
        self._opacity_anim.setStartValue(0.0)
        self._opacity_anim.setEndValue(1.0)
        self._opacity_anim.start()

    def fade_out_and_close(self) -> None:
        self._should_close = True
        self._opacity_anim.stop()
        self._opacity_anim.setStartValue(1.0)
        self._opacity_anim.setEndValue(0.0)
        self._opacity_anim.start()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.closed.emit()
        super().closeEvent(event)

    def _handle_animation_finished(self) -> None:
        if self._should_close:
            self.close()


class ToastManager(QObject):
    """Manage transient toast notifications anchored to a parent widget."""

    def __init__(
        self,
        parent: QWidget,
        *,
        theme: Optional["ThemeManager"] = None,
        margin: int = 24,
    ) -> None:
        super().__init__(parent)
        self._parent = parent
        self._margin = margin
        self._theme = theme
        self._container = QWidget(parent)
        self._container.setObjectName("ToastContainer")
        self._container.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._container.hide()

        layout = QVBoxLayout(self._container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)

        parent.installEventFilter(self)

    # ----------------------------------------------------------------- Public API

    def show_toast(
        self,
        text: str,
        *,
        level: ToastLevel = ToastLevel.INFO,
        duration_ms: int = 4500,
    ) -> None:
        message = ToastMessage(text=text, level=level, duration_ms=duration_ms)
        toast = ToastWidget(message, parent=self._container)
        toast.closed.connect(lambda: self._remove_toast(toast))

        container_layout: QVBoxLayout = self._container.layout()  # type: ignore[assignment]
        container_layout.addWidget(toast, alignment=Qt.AlignmentFlag.AlignRight)
        self._container.show()
        self._relocate()

        toast.fade_in()
        timer = QTimer(toast)
        timer.setSingleShot(True)
        timer.setInterval(duration_ms)
        timer.timeout.connect(toast.fade_out_and_close)
        timer.start()

    # ----------------------------------------------------------------- Qt events

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._parent and event.type() in {
            QEvent.Type.Resize,
            QEvent.Type.Move,
            QEvent.Type.Show,
        }:
            self._relocate()
        return super().eventFilter(watched, event)

    # ------------------------------------------------------------------ Helpers

    def _remove_toast(self, toast: ToastWidget) -> None:
        layout = self._container.layout()
        if layout is None:
            return
        layout.removeWidget(toast)
        toast.deleteLater()
        if layout.count() == 0:
            self._container.hide()

    def _relocate(self) -> None:
        if not self._container.isVisible():
            return
        parent = self._parent
        if parent is None:
            return
        self._container.adjustSize()
        rect = parent.rect()
        x = rect.right() - self._container.width() - self._margin
        y = rect.bottom() - self._container.height() - self._margin
        self._container.move(max(x, self._margin), max(y, self._margin))


__all__ = ["ToastManager", "ToastLevel", "ToastMessage"]
