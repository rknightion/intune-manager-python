"""Configuration helpers for the Intune Manager application."""

from .settings import DEFAULT_GRAPH_SCOPES, Settings, SettingsManager
from .onboarding import FirstRunStatus, detect_first_run

__all__ = [
    "DEFAULT_GRAPH_SCOPES",
    "Settings",
    "SettingsManager",
    "FirstRunStatus",
    "detect_first_run",
]
