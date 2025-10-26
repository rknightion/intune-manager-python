"""Reusable UI components for the Intune Manager PySide6 application."""

from .assignment_bridge import clear_groups, consume_groups, stage_groups
from .badges import TenantBadge
from .command_palette import CommandPalette
from .commands import CommandAction, CommandRegistry
from .context import UIContext
from .dialogs import (
    ask_confirmation,
    open_file_dialog,
    save_file_dialog,
    show_error_dialog,
    show_info_dialog,
)
from .layouts import PageScaffold, SectionHeader, make_toolbar_button
from .notifications import ToastLevel, ToastManager
from .status import InlineStatusMessage
from .shortcuts import ShortcutDefinition, ShortcutHelpDialog
from .overlays import BusyOverlay
from .progress import ProgressDialog
from .theme import (
    ThemeManager,
    ThemeName,
    SPACING_XS,
    SPACING_SM,
    SPACING_MD,
    SPACING_LG,
    SPACING_XL,
)
from .time import format_relative_timestamp

__all__ = [
    "TenantBadge",
    "stage_groups",
    "consume_groups",
    "clear_groups",
    "CommandPalette",
    "CommandAction",
    "CommandRegistry",
    "UIContext",
    "ask_confirmation",
    "open_file_dialog",
    "save_file_dialog",
    "show_error_dialog",
    "show_info_dialog",
    "PageScaffold",
    "SectionHeader",
    "make_toolbar_button",
    "ToastLevel",
    "ToastManager",
    "InlineStatusMessage",
    "ShortcutDefinition",
    "ShortcutHelpDialog",
    "BusyOverlay",
    "ProgressDialog",
    "ThemeManager",
    "ThemeName",
    "SPACING_XS",
    "SPACING_SM",
    "SPACING_MD",
    "SPACING_LG",
    "SPACING_XL",
    "format_relative_timestamp",
]
