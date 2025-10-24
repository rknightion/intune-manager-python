from __future__ import annotations

from collections.abc import Callable
from typing import Iterable, List

from intune_manager.data import ManagedDevice
from intune_manager.graph.requests import DeviceActionName
from intune_manager.services import DeviceService, ServiceErrorEvent, ServiceRegistry
from intune_manager.services.devices import DeviceActionEvent, DeviceRefreshProgressEvent
from intune_manager.utils import CancellationToken


class DeviceController:
    """Bridge between the devices UI and the underlying service layer."""

    def __init__(self, services: ServiceRegistry) -> None:
        self._services = services
        self._service: DeviceService | None = services.devices
        self._subscriptions: list[Callable[[], None]] = []

    # ----------------------------------------------------------------- Events

    def register_callbacks(
        self,
        *,
        refreshed: Callable[[Iterable[ManagedDevice], bool], None] | None = None,
        error: Callable[[ServiceErrorEvent], None] | None = None,
        action: Callable[[DeviceActionEvent], None] | None = None,
        progress: Callable[[DeviceRefreshProgressEvent], None] | None = None,
    ) -> None:
        if self._service is None:
            return
        if refreshed is not None:
            self._subscriptions.append(
                self._service.refreshed.subscribe(
                    lambda event: refreshed(event.items, event.from_cache),
                ),
            )
        if error is not None:
            self._subscriptions.append(self._service.errors.subscribe(error))
        if action is not None:
            self._subscriptions.append(self._service.actions.subscribe(action))
        if progress is not None:
            self._subscriptions.append(self._service.refresh_progress.subscribe(progress))

    def dispose(self) -> None:
        while self._subscriptions:
            unsubscribe = self._subscriptions.pop()
            try:
                unsubscribe()
            except Exception:  # pragma: no cover - best effort cleanup
                pass

    # ----------------------------------------------------------------- Queries

    def list_cached(self, tenant_id: str | None = None) -> list[ManagedDevice]:
        if self._service is None:
            return []
        return self._service.list_cached(tenant_id=tenant_id)

    def is_cache_stale(self, tenant_id: str | None = None) -> bool:
        if self._service is None:
            return True
        return self._service.is_cache_stale(tenant_id=tenant_id)

    def available_actions(self) -> List[DeviceActionName]:
        return ["syncDevice", "retire", "wipe", "rebootNow", "shutDown"]

    # ----------------------------------------------------------------- Actions

    async def refresh(
        self,
        tenant_id: str | None = None,
        *,
        force: bool = False,
        cancellation_token: CancellationToken | None = None,
    ) -> list[ManagedDevice]:
        if self._service is None:
            raise RuntimeError("Device service is not configured")
        return await self._service.refresh(
            tenant_id=tenant_id,
            force=force,
            cancellation_token=cancellation_token,
        )

    async def perform_action(
        self,
        device_id: str,
        action: DeviceActionName,
        *,
        tenant_id: str | None = None,
        parameters: dict[str, object] | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        if self._service is None:
            raise RuntimeError("Device service is not configured")
        await self._service.perform_action(
            device_id,
            action,
            tenant_id=tenant_id,
            parameters=parameters,
            cancellation_token=cancellation_token,
        )


__all__ = ["DeviceController"]
