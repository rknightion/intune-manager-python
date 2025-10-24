from __future__ import annotations

import base64
import json
from typing import Iterable

import pytest

from intune_manager.graph.errors import AuthenticationError

from tests.factories import configure_auth_manager, make_settings
from tests.stubs import StubPublicClientApplication


def _make_jwt(scopes: Iterable[str]) -> str:
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "none"}).encode("utf-8")
    ).rstrip(b"=")
    payload = base64.urlsafe_b64encode(
        json.dumps({"scp": " ".join(scopes)}).encode("utf-8")
    ).rstrip(b"=")
    return f"{header.decode('utf-8')}.{payload.decode('utf-8')}.signature"


def test_configure_initialises_msal_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    settings = make_settings()
    settings.token_cache_path = tmp_path / "cache.bin"
    stub = StubPublicClientApplication(
        client_id="",
        authority="",
        accounts=[],
    )

    manager = configure_auth_manager(
        settings=settings, stub_app=stub, monkeypatch=monkeypatch
    )

    assert stub.client_id == settings.client_id
    assert stub.authority == settings.derive_authority()
    assert manager.current_user() is None


def test_configure_requires_client_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    settings = make_settings(client_id=None)
    settings.token_cache_path = tmp_path / "cache.bin"
    stub = StubPublicClientApplication(client_id="", authority="", accounts=[])
    with pytest.raises(AuthenticationError):
        configure_auth_manager(
            settings=settings, stub_app=stub, monkeypatch=monkeypatch
        )


@pytest.mark.asyncio
async def test_acquire_token_prefers_silent(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    settings = make_settings()
    settings.graph_scopes = ["scope.read", "scope.write"]
    settings.token_cache_path = tmp_path / "cache.bin"

    access_token = _make_jwt(settings.graph_scopes)
    stub = StubPublicClientApplication(
        client_id="",
        authority="",
        accounts=[
            {
                "name": "Graph Admin",
                "username": "admin@contoso.com",
                "home_account_id": "home-account",
                "environment": "contoso.onmicrosoft.com",
            }
        ],
        silent_results=[
            {
                "access_token": access_token,
                "expires_in": 3600,
                "id_token_claims": {
                    "name": "Graph Admin",
                    "preferred_username": "admin@contoso.com",
                    "oid": "object-id",
                    "tid": "contoso-tenant",
                },
            }
        ],
        interactive_results=[],
    )

    manager = configure_auth_manager(
        settings=settings, stub_app=stub, monkeypatch=monkeypatch
    )
    token = await manager.acquire_token(settings.graph_scopes)

    assert token.token == access_token
    assert token.expires_on > 0
    assert len(stub.acquire_token_silent_calls) == 1
    assert len(stub.acquire_token_interactive_calls) == 0
    user = manager.current_user()
    assert user is not None
    assert user.username == "admin@contoso.com"
    assert manager.missing_scopes() == []


@pytest.mark.asyncio
async def test_acquire_token_interactive_when_silent_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    settings = make_settings()
    settings.graph_scopes = ["scope.read"]
    settings.token_cache_path = tmp_path / "cache.bin"
    granted_scopes = ["scope.read"]
    access_token = _make_jwt(granted_scopes)

    stub = StubPublicClientApplication(
        client_id="",
        authority="",
        accounts=[
            {
                "name": "Cached User",
                "username": "cached@contoso.com",
                "home_account_id": "cached-account",
                "environment": "tenant-xyz",
            }
        ],
        silent_results=[],
        interactive_results=[
            {
                "access_token": access_token,
                "expires_on": 1700000000,
                "id_token_claims": {
                    "name": "Interactive User",
                    "preferred_username": "user@contoso.com",
                    "oid": "oid-123",
                    "tid": "tenant-xyz",
                },
            }
        ],
    )

    manager = configure_auth_manager(
        settings=settings, stub_app=stub, monkeypatch=monkeypatch
    )
    token = await manager.acquire_token(settings.graph_scopes)

    assert token.token == access_token
    assert len(stub.acquire_token_silent_calls) == 1  # attempted
    assert len(stub.acquire_token_interactive_calls) == 1
    user = manager.current_user()
    assert user is not None
    assert user.tenant_id == "tenant-xyz"
    assert manager.missing_scopes() == []


def test_acquire_token_sync_requires_prior_interactive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    settings = make_settings()
    settings.graph_scopes = ["scope.read"]
    settings.token_cache_path = tmp_path / "cache.bin"
    stub = StubPublicClientApplication(
        client_id="",
        authority="",
        accounts=[],
        silent_results=[],
        interactive_results=[],
    )
    manager = configure_auth_manager(
        settings=settings, stub_app=stub, monkeypatch=monkeypatch
    )

    with pytest.raises(AuthenticationError):
        manager.acquire_token_sync(settings.graph_scopes)


@pytest.mark.asyncio
async def test_sign_out_clears_cached_user(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    settings = make_settings()
    settings.graph_scopes = ["scope.read"]
    settings.token_cache_path = tmp_path / "cache.bin"
    access_token = _make_jwt(settings.graph_scopes)

    stub = StubPublicClientApplication(
        client_id="",
        authority="",
        accounts=[
            {
                "name": "Graph Admin",
                "username": "admin@contoso.com",
                "home_account_id": "home-account",
                "environment": "contoso.onmicrosoft.com",
            }
        ],
        silent_results=[
            {
                "access_token": access_token,
                "expires_in": 3600,
                "id_token_claims": {
                    "name": "Graph Admin",
                    "preferred_username": "admin@contoso.com",
                    "oid": "object-id",
                    "tid": "contoso-tenant",
                },
            }
        ],
    )

    manager = configure_auth_manager(
        settings=settings, stub_app=stub, monkeypatch=monkeypatch
    )
    await manager.acquire_token(settings.graph_scopes)
    assert manager.current_user() is not None
    settings.token_cache_path.write_text("{}", encoding="utf-8")
    assert settings.token_cache_path.exists()
    await manager.sign_out()
    assert manager.current_user() is None
    assert manager.missing_scopes() == []
    assert not settings.token_cache_path.exists()
