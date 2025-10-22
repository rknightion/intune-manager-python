from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Literal, TypedDict

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

ThemeName = Literal["light", "dark"]


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
        background="#f5f7fb",
        surface="#ffffff",
        surface_alt="#f0f2f6",
        border="#d5dae3",
        text="#1b1f24",
        text_muted="#5f6673",
        accent="#0063b1",
        accent_contrast="#ffffff",
        success="#1b8651",
        warning="#c15d12",
        error="#c92a2a",
        shadow="rgba(15, 23, 42, 0.18)",
    ),
    "dark": ThemeTokens(
        background="#10131a",
        surface="#161b22",
        surface_alt="#1f242d",
        border="#292f3b",
        text="#e6ebf5",
        text_muted="#a0a8b8",
        accent="#3399ff",
        accent_contrast="#05101a",
        success="#2fc978",
        warning="#ffa24c",
        error="#ff6b6b",
        shadow="rgba(8, 11, 19, 0.72)",
    ),
}


def _palette_from_tokens(tokens: ThemeTokens) -> QPalette:
    palette = QPalette()
    background = QColor(tokens["background"])
    surface = QColor(tokens["surface"])
    text = QColor(tokens["text"])
    text_muted = QColor(tokens["text_muted"])

    palette.setColor(QPalette.Window, background)
    palette.setColor(QPalette.WindowText, text)
    palette.setColor(QPalette.Base, surface)
    palette.setColor(QPalette.AlternateBase, QColor(tokens["surface_alt"]))
    palette.setColor(QPalette.ToolTipBase, surface)
    palette.setColor(QPalette.ToolTipText, text)
    palette.setColor(QPalette.Text, text)
    palette.setColor(QPalette.Button, surface)
    palette.setColor(QPalette.ButtonText, text)
    palette.setColor(QPalette.BrightText, QColor(tokens["accent_contrast"]))
    palette.setColor(QPalette.Link, QColor(tokens["accent"]))
    palette.setColor(QPalette.Highlight, QColor(tokens["accent"]))
    palette.setColor(QPalette.HighlightedText, QColor(tokens["accent_contrast"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.WindowText, text_muted)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.Text, text_muted)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ButtonText, text_muted)
    return palette


@dataclass(slots=True)
class ThemeState:
    """Small container to expose theme state to widgets."""

    name: ThemeName
    tokens: ThemeTokens


class ThemeManager(QObject):
    """Manage application theme (light/dark) and notify listeners."""

    themeChanged = Signal(str)

    def __init__(
        self,
        *,
        app: QApplication | None = None,
        default: ThemeName = "light",
    ) -> None:
        super().__init__()
        self._app = app or QApplication.instance()
        self._state = ThemeState(name=default, tokens=_THEME_MAP[default])
        if self._app is not None:
            self._app.setStyle("Fusion")
            self._app.setPalette(_palette_from_tokens(self._state.tokens))

    # ----------------------------------------------------------------- Accessors

    @property
    def current(self) -> ThemeState:
        return self._state

    def tokens(self) -> ThemeTokens:
        return self._state.tokens

    # --------------------------------------------------------------- Manipulators

    def set_theme(self, name: ThemeName) -> None:
        if name == self._state.name:
            return
        tokens = _THEME_MAP.get(name)
        if tokens is None:
            raise ValueError(f"Unsupported theme name: {name}")
        self._state = ThemeState(name=name, tokens=tokens)
        if self._app is not None:
            self._app.setPalette(_palette_from_tokens(tokens))
        self.themeChanged.emit(name)

    def toggle(self) -> ThemeName:
        """Toggle between light and dark themes."""

        next_theme: ThemeName = "dark" if self._state.name == "light" else "light"
        self.set_theme(next_theme)
        return next_theme

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
                color: {tokens['text']};
            }}
            QFrame#Card {{
                background-color: {tokens['surface']};
                border: 1px solid {tokens['border']};
                border-radius: 10px;
            }}
            QLabel[class='page-title'] {{
                font-size: 24px;
                font-weight: 600;
            }}
            QLabel[class='page-subtitle'] {{
                color: {tokens['text_muted']};
            }}
            QListWidget#NavigationList::item:selected {{
                background-color: {tokens['accent']};
                color: {tokens['accent_contrast']};
            }}
            QListWidget#NavigationList::item:hover {{
                background-color: {tokens['surface_alt']};
            }}
        """


__all__ = ["ThemeManager", "ThemeName", "ThemeTokens"]
