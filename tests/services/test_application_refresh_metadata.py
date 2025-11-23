from __future__ import annotations

import asyncio

import pytest

from intune_manager.data import AttachmentCache, MobileAppRepository
from intune_manager.data.models import MobileApp
from intune_manager.data.models.application import MobileAppPlatform
from intune_manager.services.applications import ApplicationService


class _StubRepository(MobileAppRepository):
    def __init__(self, cached: list[MobileApp]) -> None:
        # Database is never touched in this stub; parent needs a db object, so provide None
        super().__init__(db=None)  # type: ignore[arg-type]
        self._cached = cached
        self.replaced: list[MobileApp] | None = None

    def list_all(self, tenant_id: str | None = None):  # type: ignore[override]
        return list(self._cached)

    def is_cache_stale(self, tenant_id: str | None = None):  # type: ignore[override]
        return False

    def replace_all(  # type: ignore[override]
        self,
        models: list[MobileApp],
        *,
        tenant_id: str | None = None,
        expires_in=None,
    ):
        self.replaced = models


class _StubClientFactory:
    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = payloads

    async def iter_collection(self, *_args, **_kwargs):
        for payload in self.payloads:
            yield payload


@pytest.mark.asyncio
async def test_refresh_forces_when_cached_metadata_missing(tmp_path):
    cached = [
        MobileApp(id="app-1", display_name="Old App", app_type=None, platform_type=None)
    ]
    repo = _StubRepository(cached)
    client = _StubClientFactory(
        [
            {
                "id": "app-1",
                "displayName": "Old App",
                "@odata.type": "#microsoft.graph.macOsVppApp",
            }
        ]
    )
    attachments = AttachmentCache(base_dir=tmp_path / "attachments")
    service = ApplicationService(client, repo, attachments)

    result = await service.refresh(tenant_id="tenant-1", force=False)

    assert repo.replaced is not None, "Refresh should replace cache when metadata missing"
    assert result[0].platform_type == MobileAppPlatform.MACOS
    assert result[0].app_type == "VPP"


@pytest.mark.asyncio
async def test_refresh_infers_metadata_from_app_store_url(tmp_path):
    cached = [
        MobileApp(
            id="app-2",
            display_name="Mac App Store item",
            app_type=None,
            platform_type=None,
            information_url="https://apps.apple.com/gb/app/example/id123?mt=12",
        )
    ]
    repo = _StubRepository(cached)
    client = _StubClientFactory(
        [
            {
                "id": "app-2",
                "displayName": "Mac App Store item",
                # intentionally missing @odata.type to exercise inference
                "informationUrl": "https://apps.apple.com/gb/app/example/id123?mt=12",
            }
        ]
    )
    attachments = AttachmentCache(base_dir=tmp_path / "attachments")
    service = ApplicationService(client, repo, attachments)

    result = await service.refresh(tenant_id="tenant-1", force=False)

    assert result[0].platform_type == MobileAppPlatform.MACOS
    assert result[0].app_type == "Store"
