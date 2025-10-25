from __future__ import annotations

import os
from typing import Final

import keyring
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

from intune_manager.config.settings import APP_NAME
from intune_manager.utils import get_logger


logger = get_logger(__name__)

_ALLOW_INSECURE_ENV: Final[str] = "INTUNE_MANAGER_ALLOW_INSECURE_KEYRING"


class InsecureKeyringError(RuntimeError):
    """Raised when the active keyring backend does not provide encryption."""


def _describe_backend(backend: KeyringBackend) -> str:
    return f"{backend.__class__.__module__}.{backend.__class__.__name__}"


def _is_secure_backend(backend: KeyringBackend) -> bool:
    secure_flag = getattr(backend, "secure_storage", None)
    if secure_flag is True:
        return True
    if secure_flag is False:
        return False

    name = backend.__class__.__name__.lower()
    module = backend.__class__.__module__
    if any(
        token in name
        for token in ("plaintext", "unencrypted", "insecure", "simplekeyring")
    ):
        return False
    if module.startswith("keyring.backends.chainer"):
        children = getattr(backend, "backends", ())
        if not children:
            return False
        return all(_is_secure_backend(child) for child in children)
    if module.startswith(
        (
            "keyring.backends.file",
            "keyrings.alt.file",
            "keyring.backends.null",
            "keyring.backends.fail",
        )
    ):
        return False
    return True


def _allow_insecure_setting(flag: bool | None) -> bool:
    if flag is not None:
        return flag
    env = os.getenv(_ALLOW_INSECURE_ENV)
    if env is None:
        return False
    return env.strip().lower() in {"1", "true", "yes", "on"}


class SecretStore:
    """Wraps OS keyring access for configuration secrets."""

    def __init__(
        self,
        service_name: str = APP_NAME,
        *,
        backend: KeyringBackend | None = None,
        allow_insecure: bool | None = None,
    ) -> None:
        self._service_name = service_name
        self._backend = backend or keyring.get_keyring()
        self._enforce_backend_security(allow_insecure)

        # Log backend info for diagnostics (especially useful in compiled builds)
        logger.info(
            "Keyring backend initialized",
            backend=_describe_backend(self._backend),
            service=service_name,
            secure=_is_secure_backend(self._backend),
        )

    def get_secret(self, key: str) -> str | None:
        return self._backend.get_password(self._service_name, key)

    def set_secret(self, key: str, value: str) -> None:
        self._backend.set_password(self._service_name, key, value)

    def delete_secret(self, key: str) -> None:
        try:
            self._backend.delete_password(self._service_name, key)
        except PasswordDeleteError:  # pragma: no cover - platform specific
            pass

    # ----------------------------------------------------------------- Helpers

    def _enforce_backend_security(self, allow_insecure: bool | None) -> None:
        descriptor = _describe_backend(self._backend)
        if _is_secure_backend(self._backend):
            logger.debug("Using secure keyring backend", backend=descriptor)
            return
        if _allow_insecure_setting(allow_insecure):
            logger.warning(
                "Proceeding with insecure keyring backend due to override",
                backend=descriptor,
                env=_ALLOW_INSECURE_ENV,
            )
            return

        # Provide helpful error message for compiled environments
        error_msg = f"Keyring backend {descriptor} does not provide encrypted storage."
        if "fail" in descriptor.lower():
            error_msg += (
                " This typically occurs in compiled executables when system keyring "
                "dependencies are missing. On Windows, ensure pywin32-ctypes>=0.2.0 is installed. "
                f"For development/testing, set {_ALLOW_INSECURE_ENV}=1 to bypass this check."
            )
        raise InsecureKeyringError(error_msg)


__all__ = ["SecretStore", "InsecureKeyringError"]
