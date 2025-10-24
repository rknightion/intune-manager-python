from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Literal, TypedDict

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

ThemeName = Literal["light"]


# Spacing system for consistent layout throughout the application
SPACING_XS = 4  # Tight spacing for closely related items
SPACING_SM = 8  # Compact spacing for component internals
SPACING_MD = 12  # Default spacing between related elements
SPACING_LG = 16  # Section spacing, breathing room
SPACING_XL = 24  # Page margins and major section separators


class ThemeTokens(TypedDict):
    """Tokenised color palette used across UI widgets."""

    background: str
    surface: str
    surface_alt: str
    border: str
    text: str
    text_muted: str
    accent: str
    accent_contrast: str
    success: str
    warning: str
    error: str
    shadow: str


_THEME_MAP: Dict[ThemeName, ThemeTokens] = {
    "light": ThemeTokens(
        background="#ffffff",  # Changed to white (was #f5f7fb grey)
        surface="#ffffff",
        surface_alt="#f5f7fb",  # Light grey for alternating/sidebar
        border="#d5dae3",
        text="#1b1f24",
        text_muted="#5f6673",
        accent="#0063b1",
        accent_contrast="#ffffff",
        success="#1b8651",
        warning="#a84d0e",  # Darkened for better contrast (was #c15d12)
        error="#c92a2a",
        shadow="rgba(15, 23, 42, 0.18)",
    ),
}


def _palette_from_tokens(tokens: ThemeTokens) -> QPalette:
    palette = QPalette()
    background = QColor(tokens["background"])
    surface = QColor(tokens["surface"])
    text = QColor(tokens["text"])
    text_muted = QColor(tokens["text_muted"])

    palette.setColor(QPalette.ColorRole.Window, background)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, surface)
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(tokens["surface_alt"]))
    palette.setColor(QPalette.ColorRole.ToolTipBase, surface)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, surface)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.BrightText, QColor(tokens["accent_contrast"]))
    palette.setColor(QPalette.ColorRole.Link, QColor(tokens["accent"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(tokens["accent"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(tokens["accent_contrast"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, text_muted)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, text_muted)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, text_muted)
    return palette


@dataclass(slots=True)
class ThemeState:
    """Small container to expose theme state to widgets."""

    name: ThemeName
    tokens: ThemeTokens


class ThemeManager(QObject):
    """Manage the application light theme and notify listeners."""

    themeChanged = Signal(str)

    def __init__(
        self,
        *,
        app: QApplication | None = None,
    ) -> None:
        super().__init__()
        self._app = app or QApplication.instance()
        self._state = ThemeState(name="light", tokens=_THEME_MAP["light"])
        if self._app is not None:
            self._app.setStyle("Fusion")  # type: ignore[attr-defined]
            self._app.setPalette(_palette_from_tokens(self._state.tokens))

    # ----------------------------------------------------------------- Accessors

    @property
    def current(self) -> ThemeState:
        return self._state

    def tokens(self) -> ThemeTokens:
        return self._state.tokens

    # --------------------------------------------------------------- Manipulators

    def set_theme(self, name: str) -> None:
        target = name if name in _THEME_MAP else "light"
        if target == self._state.name:
            return
        tokens = _THEME_MAP["light"]
        self._state = ThemeState(name="light", tokens=tokens)
        if self._app is not None:
            self._app.setPalette(_palette_from_tokens(tokens))  # type: ignore[attr-defined]
        self.themeChanged.emit("light")

    # ---------------------------------------------------------------- Utilities

    def css_variables(self) -> str:
        """Return a string defining CSS custom properties for the active theme."""

        tokens = self._state.tokens
        return (
            ":root {{"
            "  --surface: {surface};"
            "  --surface-alt: {surface_alt};"
            "  --border: {border};"
            "  --text-primary: {text};"
            "  --text-muted: {text_muted};"
            "  --accent: {accent};"
            "  --accent-contrast: {accent_contrast};"
            "  --success: {success};"
            "  --warning: {warning};"
            "  --error: {error};"
            "}}"
        ).format(**tokens)

    def apply_to(self, widget: QObject) -> None:
        """Apply palette-aware stylesheet helpers to a widget."""

        if not hasattr(widget, "setStyleSheet"):
            return
        widget.setStyleSheet(self.base_stylesheet())

    def base_stylesheet(self) -> str:
        tokens = self._state.tokens
        return f"""
            QWidget {{
                color: {tokens["text"]};
                background-color: {tokens["background"]};
            }}
            QLabel {{
                background: transparent;
            }}
            QFrame#Card {{
                background-color: {tokens["surface"]};
                border: 1px solid {tokens["border"]};
                border-radius: 10px;
            }}
            QLabel[class='page-title'] {{
                font-size: 24px;
                font-weight: 600;
                background: transparent;
            }}
            QLabel[class='page-subtitle'] {{
                color: {tokens["text_muted"]};
                background: transparent;
            }}
            QPushButton, QToolButton {{
                background-color: {tokens["surface"]};
                border: 1px solid {tokens["border"]};
                border-radius: 6px;
                padding: 6px 12px;
            }}
            QPushButton:disabled, QToolButton:disabled {{
                color: {tokens["text_muted"]};
                border-color: {tokens["border"]};
            }}
            QPushButton:focus, QToolButton:focus {{
                border: 2px solid {tokens["accent"]};
            }}
            QLineEdit, QComboBox, QTextEdit, QPlainTextEdit {{
                background-color: {tokens["surface"]};
                border: 1px solid {tokens["border"]};
                border-radius: 6px;
                padding: 6px 8px;
            }}
            QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
                border: 2px solid {tokens["accent"]};
            }}
            QFocusFrame {{
                border: 2px solid {tokens["accent"]};
                border-radius: 6px;
            }}
            QListWidget, QTreeWidget, QTableView {{
                background-color: {tokens["surface"]};
                border: 1px solid {tokens["border"]};
                border-radius: 6px;
            }}
            QListWidget:focus, QTreeWidget:focus, QTableView:focus {{
                border: 2px solid {tokens["accent"]};
            }}
            QListWidget#NavigationList {{
                background-color: {tokens["surface_alt"]};
            }}
            QListWidget#NavigationList::item:selected {{
                background-color: {tokens["accent"]};
                color: {tokens["accent_contrast"]};
            }}
            QListWidget#NavigationList::item:hover {{
                background-color: {tokens["background"]};
            }}
        """


__all__ = [
    "ThemeManager",
    "ThemeName",
    "ThemeTokens",
    "SPACING_XS",
    "SPACING_SM",
    "SPACING_MD",
    "SPACING_LG",
    "SPACING_XL",
]
