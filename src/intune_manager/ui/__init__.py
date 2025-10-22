"""UI package for the Intune Manager application."""

from .applications import ApplicationsWidget
from .assignments import AssignmentsWidget
from .devices import DevicesWidget
from .groups import GroupsWidget
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
    "DevicesWidget",
    "ApplicationsWidget",
    "GroupsWidget",
    "AssignmentsWidget",
    "MainWindow",
    "NavigationItem",
]
