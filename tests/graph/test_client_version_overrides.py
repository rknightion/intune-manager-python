from __future__ import annotations

from intune_manager.auth.types import AccessToken
from intune_manager.graph.client import (
    GraphAPIVersion,
    GraphClientConfig,
    GraphClientFactory,
)


def _token_provider(_scopes: object) -> AccessToken:
    return AccessToken("token", 0)


def test_mobile_apps_use_beta_version() -> None:
    config = GraphClientConfig(scopes=[".default"])
    factory = GraphClientFactory(_token_provider, config)

    assert (
        factory.resolve_api_version("/deviceAppManagement/mobileApps")
        == GraphAPIVersion.BETA.value
    )
    assert (
        factory.resolve_api_version(
            "/deviceAppManagement/mobileApps/app-1/assignments"
        )
        == GraphAPIVersion.BETA.value
    )
