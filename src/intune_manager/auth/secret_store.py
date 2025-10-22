from __future__ import annotations

import keyring

from intune_manager.config.settings import APP_NAME


class SecretStore:
    """Wraps OS keyring access for configuration secrets."""

    def __init__(self, service_name: str = APP_NAME) -> None:
        self._service_name = service_name

    def get_secret(self, key: str) -> str | None:
        return keyring.get_password(self._service_name, key)

    def set_secret(self, key: str, value: str) -> None:
        keyring.set_password(self._service_name, key, value)

    def delete_secret(self, key: str) -> None:
        try:
            keyring.delete_password(self._service_name, key)
        except (
            keyring.errors.PasswordDeleteError
        ):  # pragma: no cover - platform specific
            pass


__all__ = ["SecretStore"]
