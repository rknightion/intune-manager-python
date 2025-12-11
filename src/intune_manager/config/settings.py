from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv
from platformdirs import user_cache_dir, user_config_dir

APP_NAME = "IntuneManager"
ENV_PREFIX = "INTUNE_MANAGER_"
ENV_FILE_NAME = "settings.env"
TOKEN_CACHE_NAME = "token_cache.bin"
BROKER_DB_NAME = "tasks.db"

DEFAULT_GRAPH_SCOPES: tuple[str, ...] = (
    "https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/DeviceManagementManagedDevices.Read.All",
    "https://graph.microsoft.com/DeviceManagementManagedDevices.ReadWrite.All",
    "https://graph.microsoft.com/DeviceManagementManagedDevices.PrivilegedOperations.All",
    "https://graph.microsoft.com/DeviceManagementApps.Read.All",
    "https://graph.microsoft.com/DeviceManagementApps.ReadWrite.All",
    "https://graph.microsoft.com/DeviceManagementConfiguration.Read.All",
    "https://graph.microsoft.com/DeviceManagementConfiguration.ReadWrite.All",
    "https://graph.microsoft.com/Group.Read.All",
    "https://graph.microsoft.com/Group.ReadWrite.All",
    "https://graph.microsoft.com/GroupMember.Read.All",
    "https://graph.microsoft.com/AuditLog.Read.All",
)


def _config_dir() -> Path:
    path = Path(user_config_dir(APP_NAME, roaming=True))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cache_dir() -> Path:
    path = Path(user_cache_dir(APP_NAME))
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_dir() -> Path:
    return _config_dir()


def cache_dir() -> Path:
    return _cache_dir()


def log_dir() -> Path:
    path = cache_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def runtime_dir() -> Path:
    path = cache_dir() / "runtime"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _env_file_path(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    return _config_dir() / ENV_FILE_NAME


@dataclass(slots=True)
class Settings:
    """Container for tenant/app registration data required by MSAL and Graph.

    This application uses MSAL Public Client authentication, which does NOT require
    a client secret. Your Azure AD app registration should be configured as
    "Mobile and desktop applications" (not "Web application").
    """

    tenant_id: str | None = None
    client_id: str | None = None
    redirect_uri: str | None = None
    authority: str | None = None
    graph_scopes: list[str] = field(default_factory=lambda: list(DEFAULT_GRAPH_SCOPES))
    token_cache_path: Path = field(
        default_factory=lambda: _cache_dir() / TOKEN_CACHE_NAME
    )

    def configured_scopes(self) -> Iterable[str]:
        """Return deduplicated scopes preserving order (includes new defaults)."""

        merged: list[str] = list(self.graph_scopes) + [
            scope for scope in DEFAULT_GRAPH_SCOPES if scope not in self.graph_scopes
        ]
        seen = set[str]()
        for scope in merged:
            if scope and scope not in seen:
                seen.add(scope)
                yield scope

    @property
    def is_configured(self) -> bool:
        """True when mandatory tenant + client identifiers are set."""
        return bool(self.tenant_id and self.client_id)

    def derive_authority(self) -> str:
        """Return configured authority, defaulting to common tenant."""
        if self.authority:
            return self.authority
        tenant = self.tenant_id or "common"
        return f"https://login.microsoftonline.com/{tenant}"


class SettingsManager:
    """Load and persist application settings with environment overrides."""

    def __init__(self, env_file: Path | None = None) -> None:
        self._env_file = _env_file_path(env_file)

    @property
    def env_file(self) -> Path:
        return self._env_file

    def load(self) -> Settings:
        """Load settings from environment, falling back to persisted file."""
        load_dotenv(self._env_file, override=False)

        tenant_id = self._get_env("TENANT_ID")
        client_id = self._get_env("CLIENT_ID")
        redirect_uri = self._get_env("REDIRECT_URI")
        authority = self._get_env("AUTHORITY")
        scopes = self._get_scopes_from_env()
        token_cache_override = self._get_env("TOKEN_CACHE_PATH")

        settings = Settings(
            tenant_id=tenant_id,
            client_id=client_id,
            redirect_uri=redirect_uri,
            authority=authority,
        )

        if scopes:
            settings.graph_scopes = scopes

        if token_cache_override:
            settings.token_cache_path = Path(token_cache_override).expanduser()

        return settings

    def save(self, settings: Settings) -> None:
        """Persist core configuration fields to the managed env file."""
        self._env_file.parent.mkdir(parents=True, exist_ok=True)
        content = [
            f"{ENV_PREFIX}TENANT_ID={settings.tenant_id or ''}",
            f"{ENV_PREFIX}CLIENT_ID={settings.client_id or ''}",
            f"{ENV_PREFIX}REDIRECT_URI={settings.redirect_uri or ''}",
            f"{ENV_PREFIX}AUTHORITY={settings.authority or ''}",
            f"{ENV_PREFIX}SCOPES={';'.join(settings.configured_scopes())}",
            f"{ENV_PREFIX}TOKEN_CACHE_PATH={settings.token_cache_path}",
        ]
        self._env_file.write_text("\n".join(content) + "\n", encoding="utf-8")

    def _get_env(self, name: str) -> str | None:
        return os.getenv(f"{ENV_PREFIX}{name}") or None

    def _get_scopes_from_env(self) -> list[str] | None:
        raw = self._get_env("SCOPES")
        if not raw:
            return None
        scopes = [scope.strip() for scope in raw.split(";") if scope.strip()]
        return scopes or None


__all__ = [
    "DEFAULT_GRAPH_SCOPES",
    "Settings",
    "SettingsManager",
    "cache_dir",
    "config_dir",
    "log_dir",
    "runtime_dir",
]
