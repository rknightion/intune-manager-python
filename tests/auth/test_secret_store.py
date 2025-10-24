from __future__ import annotations

import pytest
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

from intune_manager.auth import InsecureKeyringError, SecretStore


class _StubBackend(KeyringBackend):
    """In-memory keyring backend for exercising SecretStore behaviour."""

    priority = 1

    def __init__(self, *, secure: bool) -> None:
        self._store: dict[tuple[str, str], str] = {}
        self.secure_storage = secure

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        try:
            del self._store[(service, username)]
        except KeyError as exc:
            raise PasswordDeleteError("Secret missing") from exc


def test_secret_store_rejects_insecure_backend() -> None:
    backend = _StubBackend(secure=False)
    with pytest.raises(InsecureKeyringError):
        SecretStore(service_name="pytest", backend=backend)


def test_secret_store_allows_override_for_testing() -> None:
    backend = _StubBackend(secure=False)
    store = SecretStore(
        service_name="pytest",
        backend=backend,
        allow_insecure=True,
    )
    store.set_secret("token", "value")
    assert store.get_secret("token") == "value"
    store.delete_secret("token")
    assert store.get_secret("token") is None


def test_secret_round_trip_with_secure_backend() -> None:
    backend = _StubBackend(secure=True)
    store = SecretStore(service_name="pytest", backend=backend)
    assert store.get_secret("missing") is None
    store.set_secret("client_secret", "top-secret")
    assert store.get_secret("client_secret") == "top-secret"
    store.delete_secret("client_secret")
    assert store.get_secret("client_secret") is None

