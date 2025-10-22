from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class SectionHeader(QWidget):
    """Reusable header displaying a title, optional subtitle, and action widgets."""

    def __init__(
        self,
        title: str,
        *,
        subtitle: str | None = None,
        actions: Iterable[QWidget] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("PageTitle")
        self.title_label.setProperty("class", "page-title")
        font = self.title_label.font()
        font.setPointSizeF(font.pointSizeF() + 4)
        font.setWeight(600)
        self.title_label.setFont(font)

        header_row.addWidget(self.title_label)
        header_row.addStretch()

        self.action_container = QWidget()
        actions_layout = QHBoxLayout(self.action_container)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(4)

        if actions:
            for widget in actions:
                actions_layout.addWidget(widget)

        header_row.addWidget(self.action_container)
        layout.addLayout(header_row)

        if subtitle:
            self.subtitle_label = QLabel(subtitle)
            self.subtitle_label.setWordWrap(True)
            self.subtitle_label.setProperty("class", "page-subtitle")
            layout.addWidget(self.subtitle_label)
        else:
            self.subtitle_label = None

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setFrameShadow(QFrame.Sunken)
        divider.setObjectName("HeaderDivider")
        layout.addWidget(divider)

    def set_actions(self, actions: Iterable[QWidget]) -> None:
        layout = self.action_container.layout()
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for widget in actions:
            layout.addWidget(widget)


class PageScaffold(QWidget):
    """Convenience widget providing a header and body layout for modules."""

    def __init__(
        self,
        title: str,
        *,
        subtitle: str | None = None,
        actions: Iterable[QWidget] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PageScaffold")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        self.header = SectionHeader(title, subtitle=subtitle, actions=actions, parent=self)
        layout.addWidget(self.header)

        self.body = QWidget()
        self.body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(12)

        layout.addWidget(self.body, stretch=1)

    def add_body_widget(self, widget: QWidget, *, stretch: int = 0) -> None:
        self.body_layout.addWidget(widget, stretch)

    def add_body_layout(self, layout: QVBoxLayout) -> None:
        self.body_layout.addLayout(layout)


def make_toolbar_button(
    text: str,
    *,
    tooltip: str | None = None,
    icon: QIcon | None = None,
    checkable: bool = False,
) -> QToolButton:
    button = QToolButton()
    button.setText(text)
    button.setCheckable(checkable)
    button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    if tooltip:
        button.setToolTip(tooltip)
    if icon is not None:
        button.setIcon(icon)
    return button


__all__ = ["PageScaffold", "SectionHeader", "make_toolbar_button"]
