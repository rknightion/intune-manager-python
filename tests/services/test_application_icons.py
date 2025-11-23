from __future__ import annotations

import base64

import pytest

from intune_manager.data.storage import AttachmentCache
from intune_manager.graph.errors import GraphAPIError
from intune_manager.services.applications import ApplicationService


class _StubClientFactory:
    def __init__(self, encoded_icon: str) -> None:
        self.request_bytes_calls = 0
        self.request_json_calls = 0
        self._encoded_icon = encoded_icon

    async def request_bytes(self, *args, **kwargs):  # noqa: ANN002, ANN003
        self.request_bytes_calls += 1
        raise GraphAPIError("icon media route unsupported", status_code=400)

    async def request_json(self, *args, **kwargs):  # noqa: ANN002, ANN003
        self.request_json_calls += 1
        return {
            "largeIcon": {
                "@odata.type": "#microsoft.graph.mimeContent",
                "type": "image/png",
                "value": self._encoded_icon,
            }
        }


class _StubRepository:
    """Minimal stub to satisfy the ApplicationService constructor."""

    pass


@pytest.mark.asyncio
async def test_cache_icon_falls_back_to_metadata_payload(tmp_path):
    icon_bytes = b"fake-png-binary"
    encoded_icon = base64.b64encode(icon_bytes).decode("utf-8")
    client = _StubClientFactory(encoded_icon)
    attachments = AttachmentCache(base_dir=tmp_path / "attachments")
    service = ApplicationService(client, _StubRepository(), attachments)

    metadata = await service.cache_icon("app-123", tenant_id="tenant-1", force=True)

    assert metadata is not None
    assert metadata.path.exists()
    assert metadata.path.read_bytes() == icon_bytes
    assert metadata.tenant_id == "tenant-1"
    assert client.request_bytes_calls == 0
    assert client.request_json_calls == 1
