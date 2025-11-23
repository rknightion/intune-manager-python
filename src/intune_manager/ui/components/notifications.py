from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import time
from typing import Callable, Optional, TYPE_CHECKING

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
    QToolButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from .theme import ThemeManager

from intune_manager.utils import get_logger


logger = get_logger(__name__)


class ToastLevel(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


@dataclass(slots=True)
class ToastMessage:
    text: str
    level: ToastLevel = ToastLevel.INFO
    duration_ms: int | None = None
    action_label: str | None = None
    sticky: bool = False


_LEVEL_COLORS = {
    ToastLevel.INFO: ("#2563eb", "#f8fafc", "#1d4ed8"),
    ToastLevel.SUCCESS: ("#22c55e", "#042f14", "#15803d"),
    ToastLevel.WARNING: ("#f97316", "#0f172a", "#b45309"),
    ToastLevel.ERROR: ("#ef4444", "#fef2f2", "#b91c1c"),
}


class ToastWidget(QFrame):
    closed = Signal()

    def __init__(
        self,
        message: ToastMessage,
        *,
        parent: QWidget | None = None,
        action_callback: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._message = message
        self._action_callback = action_callback
        bg, fg, accent = _LEVEL_COLORS.get(
            message.level, _LEVEL_COLORS[ToastLevel.INFO]
        )

        self.setObjectName("ToastWidget")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumWidth(320)
        self.setMaximumWidth(650)
        self.setStyleSheet(
            "QFrame#ToastWidget {"
            f"  background-color: {bg};"
            "  border-radius: 12px;"
            "  padding: 12px 16px;"
            f"  color: {fg};"
            "}"
            "QLabel#ToastLabel {"
            f"  color: {fg};"
            "}"
            "QPushButton#ToastAction {"
            "  background: rgba(255, 255, 255, 0.15);"
            f"  color: {fg};"
            "  border: 1px solid rgba(255, 255, 255, 0.4);"
            "  border-radius: 8px;"
            "  padding: 4px 10px;"
            "  font-weight: 600;"
            "}"
            "QPushButton#ToastAction:hover {"
            f"  background: {accent};"
            "  color: white;"
            "  border-color: transparent;"
            "}"
            "QToolButton#ToastClose {"
            f"  color: {fg};"
            "  border: none;"
            "  font-weight: bold;"
            "  padding: 2px 4px;"
            "  background: transparent;"
            "}"
            "QToolButton#ToastClose:hover {"
            "  color: white;"
            "}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        self.label = QLabel(message.text)
        self.label.setObjectName("ToastLabel")
        self.label.setWordWrap(True)
        self.label.setMaximumWidth(600)
        self.label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self.label, stretch=1)

        self._action_button: QPushButton | None = None
        if message.action_label:
            self._action_button = QPushButton(message.action_label)
            self._action_button.setObjectName("ToastAction")
            self._action_button.clicked.connect(self._handle_action_clicked)
            layout.addWidget(self._action_button)

        self._close_button = QToolButton()
        self._close_button.setObjectName("ToastClose")
        self._close_button.setText("✕")
        self._close_button.clicked.connect(self.fade_out_and_close)
        layout.addWidget(self._close_button)

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

    def _handle_action_clicked(self) -> None:
        if self._action_callback is None:
            return
        try:
            self._action_callback()
        except Exception:
            logger.exception("Toast action failed")


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
        self._last_toast: tuple[str, ToastLevel, float] | None = None
        self._dedupe_window_s = 4.0

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
        duration_ms: int | None = None,
        action_label: str | None = None,
        on_action: Callable[[], None] | None = None,
        sticky: bool | None = None,
    ) -> ToastWidget | None:
        normalized = text.strip()
        if not normalized:
            logger.debug("Skipping empty toast message", level=level.value)
            return None
        now = time.monotonic()
        if self._last_toast is not None:
            last_text, last_level, last_timestamp = self._last_toast
            if (
                normalized == last_text
                and level == last_level
                and now - last_timestamp < self._dedupe_window_s
            ):
                logger.debug(
                    "Skipping duplicate toast",
                    level=level.value,
                    message=normalized,
                )
                return None

        resolved_sticky = sticky
        if resolved_sticky is None:
            resolved_sticky = False

        resolved_duration = duration_ms
        if resolved_duration is None and not resolved_sticky:
            resolved_duration = 7_000

        message = ToastMessage(
            text=normalized,
            level=level,
            duration_ms=resolved_duration,
            action_label=action_label,
            sticky=resolved_sticky,
        )
        toast = ToastWidget(
            message,
            parent=self._container,
            action_callback=on_action,
        )
        toast.closed.connect(lambda: self._remove_toast(toast))

        container_layout: QVBoxLayout = self._container.layout()  # type: ignore[assignment]
        container_layout.addWidget(toast, alignment=Qt.AlignmentFlag.AlignRight)
        self._container.show()

        # Defer sizing to next event loop to allow text layout to complete
        def _finalize_sizing() -> None:
            container_layout.activate()
            toast.updateGeometry()
            toast.label.updateGeometry()
            toast.adjustSize()
            self._relocate()

        QTimer.singleShot(0, _finalize_sizing)

        # Log toast to console based on level
        if level == ToastLevel.ERROR:
            logger.error(normalized, level=level.value)
        elif level == ToastLevel.WARNING:
            logger.warning(normalized, level=level.value)
        else:  # INFO and SUCCESS both use info level
            logger.info(normalized, level=level.value)

        toast.fade_in()
        self._last_toast = (normalized, level, now)
        if resolved_duration is not None and resolved_duration > 0:
            timer = QTimer(toast)
            timer.setSingleShot(True)
            timer.setInterval(resolved_duration)
            timer.timeout.connect(toast.fade_out_and_close)
            timer.start()
        return toast

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
