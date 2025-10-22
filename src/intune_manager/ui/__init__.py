"""UI package for the Intune Manager application."""

from .settings import (
    AuthStatus,
    SettingsController,
    SettingsDialog,
    SettingsSnapshot,
    SettingsWidget,
)
from .dashboard import DashboardWidget
from .main import MainWindow, NavigationItem

__all__ = [
    "AuthStatus",
    "SettingsController",
    "SettingsDialog",
    "SettingsSnapshot",
    "SettingsWidget",
    "DashboardWidget",
    "MainWindow",
    "NavigationItem",
]
