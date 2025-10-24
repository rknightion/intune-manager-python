from __future__ import annotations

from typing import Callable, Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .commands import CommandAction, CommandRegistry


CommandExecutor = Callable[[CommandAction], None]


class CommandPalette(QDialog):
    """Lightweight command palette inspired by modern productivity tooling."""

    def __init__(
        self,
        registry: CommandRegistry,
        *,
        executor: CommandExecutor,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            parent, Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
        )
        self.setModal(True)
        self.setObjectName("CommandPalette")
        self._registry = registry
        self._executor = executor
        self._actions: list[CommandAction] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search commands…")
        self.search_input.textChanged.connect(self._update_filter)
        self.search_input.returnPressed.connect(self._execute_selected)

        layout.addWidget(self.search_input)

        self.list_widget = QListWidget()
        self.list_widget.itemActivated.connect(self._execute_selected)
        layout.addWidget(self.list_widget, stretch=1)

        self.hint_label = QPushButton("Esc to close · Enter to run")
        self.hint_label.setFlat(True)
        self.hint_label.setEnabled(False)
        layout.addWidget(self.hint_label)

        self.resize(520, 360)

    # ----------------------------------------------------------------- Lifecycle

    def open_palette(self) -> None:
        self._actions = self._registry.actions()
        self._populate_list(self._actions)
        self.search_input.clear()
        self.search_input.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        self._center_in_parent()
        self.show()

    # ----------------------------------------------------------------- Internals

    def _populate_list(self, actions: Iterable[CommandAction]) -> None:
        self.list_widget.clear()
        for action in actions:
            item = QListWidgetItem(action.title)
            description = []
            if action.category:
                description.append(action.category)
            if action.description:
                description.append(action.description)
            if description:
                item.setToolTip(" — ".join(description))
            if action.shortcut:
                item.setData(Qt.ItemDataRole.UserRole + 1, action.shortcut)
                item.setText(f"{action.title}    ({action.shortcut})")
            item.setData(Qt.ItemDataRole.UserRole, action.id)
            self.list_widget.addItem(item)
        if self.list_widget.count():
            self.list_widget.setCurrentRow(0)

    def _update_filter(self, text: str) -> None:
        self._actions = self._registry.search(text)
        self._populate_list(self._actions)

    def _execute_selected(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            return
        command_id = item.data(Qt.ItemDataRole.UserRole)
        action = self._registry.get(command_id)
        if action is None:
            return
        self.hide()
        self._executor(action)

    def _center_in_parent(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        geometry = parent.frameGeometry()
        center = geometry.center()
        self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)


__all__ = ["CommandPalette", "CommandExecutor"]
