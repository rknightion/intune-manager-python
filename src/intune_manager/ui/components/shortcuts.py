from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


def _format_sequence(sequence: str) -> str:
    """Return a display-friendly shortcut string."""

    key_sequence = QKeySequence(sequence)
    text = key_sequence.toString(QKeySequence.NativeText)
    return text or sequence


@dataclass(slots=True)
class ShortcutDefinition:
    """Metadata describing an application shortcut."""

    id: str
    title: str
    sequences: Sequence[str]
    callback: Callable[[], None]
    category: str
    description: str | None = None
    show_in_palette: bool = True
    show_in_help: bool = True

    def primary_sequence(self) -> str | None:
        if not self.sequences:
            return None
        return _format_sequence(self.sequences[0])

    def display_sequences(self) -> str:
        seen = dict.fromkeys(_format_sequence(seq) for seq in self.sequences)
        return " / ".join(filter(None, seen))


class ShortcutHelpDialog(QDialog):
    """Modal overlay showing available keyboard shortcuts."""

    def __init__(
        self,
        shortcuts: Iterable[ShortcutDefinition],
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.setModal(True)
        self.resize(560, 420)
        self._shortcuts: list[ShortcutDefinition] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        intro = QLabel("Quickly navigate Intune Manager using these keyboard shortcuts.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        layout.addWidget(self._scroll, stretch=1)

        button_row = QHBoxLayout()
        button_row.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        self.set_shortcuts(shortcuts)

    # ----------------------------------------------------------------- Public

    def set_shortcuts(self, shortcuts: Iterable[ShortcutDefinition]) -> None:
        self._shortcuts = [shortcut for shortcut in shortcuts if shortcut.show_in_help]
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(12)

        by_category: dict[str, list[ShortcutDefinition]] = {}
        for shortcut in self._shortcuts:
            by_category.setdefault(shortcut.category, []).append(shortcut)

        for category, items in sorted(by_category.items()):
            group = QGroupBox(category)
            group_layout = QVBoxLayout(group)
            group_layout.setContentsMargins(12, 10, 12, 10)
            group_layout.setSpacing(6)

            for shortcut in items:
                row = QHBoxLayout()
                row.setContentsMargins(0, 0, 0, 0)
                row.setSpacing(12)

                title = QLabel(shortcut.title)
                title.setWordWrap(True)
                row.addWidget(title, stretch=3)

                keys = QLabel(shortcut.display_sequences() or "—")
                keys.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                keys.setStyleSheet("font-family: 'Menlo', 'Consolas', 'Courier New', monospace;")
                row.addWidget(keys, stretch=2)

                group_layout.addLayout(row)

                if shortcut.description:
                    description = QLabel(shortcut.description)
                    description.setWordWrap(True)
                    description.setStyleSheet("color: palette(mid); margin-left: 4px;")
                    group_layout.addWidget(description)

            container_layout.addWidget(group)

        container_layout.addStretch()
        self._scroll.takeWidget()
        self._scroll.setWidget(container)


__all__ = ["ShortcutDefinition", "ShortcutHelpDialog"]
