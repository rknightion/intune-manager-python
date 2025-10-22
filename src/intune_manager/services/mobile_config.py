from __future__ import annotations

import base64
from pathlib import Path
from typing import Iterable

from intune_manager.data import ConfigurationProfile
from intune_manager.graph.client import GraphClientFactory
from intune_manager.services.base import ServiceErrorEvent, EventHook
from intune_manager.utils import get_logger


logger = get_logger(__name__)


class MobileConfigService:
    """Helpers for working with macOS/iOS mobileconfig payloads via Graph."""

    def __init__(self, client_factory: GraphClientFactory) -> None:
        self._client_factory = client_factory
        self.errors: EventHook[ServiceErrorEvent] = EventHook()

    def load_payload(self, path: Path) -> bytes:
        data = path.read_bytes()
        logger.debug("Loaded mobileconfig payload", path=str(path), size=len(data))
        return data

    async def create_macos_custom_profile(
        self,
        *,
        display_name: str,
        payload_bytes: bytes,
        description: str | None = None,
        assignments: Iterable[dict] | None = None,
    ) -> ConfigurationProfile:
        body: dict = {
            "@odata.type": "#microsoft.graph.macOSCustomConfiguration",
            "displayName": display_name,
            "description": description,
            "payload": base64.b64encode(payload_bytes).decode("ascii"),
        }
        if assignments:
            body["assignments"] = list(assignments)

        try:
            response = await self._client_factory.request_json(
                "POST",
                "/deviceManagement/deviceConfigurations",
                json_body=body,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to create macOS custom configuration")
            self.errors.emit(ServiceErrorEvent(tenant_id=None, error=exc))
            raise

        profile = ConfigurationProfile.from_graph(response)
        logger.debug("Created macOS custom configuration", profile_id=profile.id)
        return profile

    async def update_payload(
        self,
        profile_id: str,
        *,
        payload_bytes: bytes,
        description: str | None = None,
    ) -> None:
        body: dict = {
            "payload": base64.b64encode(payload_bytes).decode("ascii"),
        }
        if description is not None:
            body["description"] = description

        try:
            await self._client_factory.request(
                "PATCH",
                f"/deviceManagement/deviceConfigurations/{profile_id}",
                json_body=body,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to update custom configuration payload", profile_id=profile_id)
            self.errors.emit(ServiceErrorEvent(tenant_id=None, error=exc))
            raise


__all__ = ["MobileConfigService"]
