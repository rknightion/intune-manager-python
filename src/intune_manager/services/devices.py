from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from intune_manager.data import DeviceRepository, ManagedDevice
from intune_manager.graph.client import GraphClientFactory
from intune_manager.graph.requests import DeviceActionName, device_action_request
from intune_manager.services.base import EventHook, RefreshEvent, ServiceErrorEvent
from intune_manager.utils import get_logger


logger = get_logger(__name__)


@dataclass(slots=True)
class DeviceActionEvent:
    tenant_id: str | None
    device_id: str
    action: DeviceActionName
    payload: dict[str, Any] | None
    success: bool
    error: Exception | None = None


@dataclass(slots=True)
class DeviceRefreshProgressEvent:
    tenant_id: str | None
    processed: int
    finished: bool = False


class DeviceService:
    """Encapsulates managed device workflows with caching and device actions."""

    def __init__(
        self,
        client_factory: GraphClientFactory,
        repository: DeviceRepository,
    ) -> None:
        self._client_factory = client_factory
        self._repository = repository
        self._default_ttl = timedelta(minutes=15)
        self._chunk_size = 200

        self.refreshed: EventHook[RefreshEvent[list[ManagedDevice]]] = EventHook()
        self.errors: EventHook[ServiceErrorEvent] = EventHook()
        self.actions: EventHook[DeviceActionEvent] = EventHook()
        self.refresh_progress: EventHook[DeviceRefreshProgressEvent] = EventHook()
        self._progress_interval = 100

    # ------------------------------------------------------------------ Queries

    def list_cached(self, tenant_id: str | None = None) -> list[ManagedDevice]:
        """Return cached managed devices."""

        items = self._repository.list_all(tenant_id=tenant_id)
        logger.debug(
            "Device cache read",
            tenant_id=tenant_id,
            count=len(items),
        )
        return items

    def is_cache_stale(self, tenant_id: str | None = None) -> bool:
        return self._repository.is_cache_stale(tenant_id=tenant_id)

    def count_cached(self, tenant_id: str | None = None) -> int:
        """Return cached device count without materialising rows."""

        return self._repository.count(tenant_id=tenant_id)

    # ----------------------------------------------------------------- Actions

    async def refresh(
        self,
        tenant_id: str | None = None,
        *,
        force: bool = False,
        expand_related: bool = True,
    ) -> list[ManagedDevice]:
        """Refresh devices from Graph when cache is stale or force requested."""

        if not force and not self.is_cache_stale(tenant_id=tenant_id):
            cached = self.list_cached(tenant_id=tenant_id)
            self.refreshed.emit(
                RefreshEvent(
                    tenant_id=tenant_id,
                    items=cached,
                    from_cache=True,
                ),
            )
            return cached

        params: dict[str, Any] | None = None
        if expand_related:
            params = {"$expand": "detectedApps"}

        processed = 0
        interval = max(50, self._chunk_size // 2)

        async def device_iterator() -> AsyncIterator[ManagedDevice]:
            nonlocal processed
            async for item in self._client_factory.iter_collection(
                "GET",
                "/deviceManagement/managedDevices",
                params=params,
            ):
                processed += 1
                if processed % interval == 0:
                    self.refresh_progress.emit(
                        DeviceRefreshProgressEvent(
                            tenant_id=tenant_id,
                            processed=processed,
                            finished=False,
                        ),
                    )
                yield ManagedDevice.from_graph(item)

        try:
            count = await self._repository.replace_all_async(
                device_iterator(),
                tenant_id=tenant_id,
                expires_in=self._default_ttl,
                chunk_size=self._chunk_size,
            )
            processed = max(processed, count)
            self.refresh_progress.emit(
                DeviceRefreshProgressEvent(
                    tenant_id=tenant_id,
                    processed=processed,
                    finished=True,
                ),
            )
            items = self.list_cached(tenant_id=tenant_id)
            self.refreshed.emit(
                RefreshEvent(
                    tenant_id=tenant_id,
                    items=items,
                    from_cache=False,
                ),
            )
            return items
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to refresh devices", tenant_id=tenant_id)
            self.errors.emit(ServiceErrorEvent(tenant_id=tenant_id, error=exc))
            raise

    async def perform_action(
        self,
        device_id: str,
        action: DeviceActionName,
        *,
        tenant_id: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> None:
        """Execute a device management action (sync, wipe, retire, reboot, shutdown)."""

        payload = parameters or {}
        request = device_action_request(device_id, action, body=payload)
        try:
            await self._client_factory.request(
                request.method,
                request.url,
                json_body=request.body,
                headers=request.headers,
                api_version=request.api_version,
            )
            event = DeviceActionEvent(
                tenant_id=tenant_id,
                device_id=device_id,
                action=action,
                payload=payload or None,
                success=True,
            )
            self.actions.emit(event)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Device action failed",
                device_id=device_id,
                action=action,
                tenant_id=tenant_id,
            )
            event = DeviceActionEvent(
                tenant_id=tenant_id,
                device_id=device_id,
                action=action,
                payload=payload or None,
                success=False,
                error=exc,
            )
            self.errors.emit(ServiceErrorEvent(tenant_id=tenant_id, error=exc))
            self.actions.emit(event)
            raise


__all__ = ["DeviceService", "DeviceActionEvent", "DeviceRefreshProgressEvent"]
