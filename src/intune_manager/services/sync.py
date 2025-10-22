from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from intune_manager.services.applications import ApplicationService
from intune_manager.services.audit import AuditLogService
from intune_manager.services.configurations import ConfigurationService
from intune_manager.services.devices import DeviceService
from intune_manager.services.filters import AssignmentFilterService
from intune_manager.services.groups import GroupService
from intune_manager.services.base import EventHook, ServiceErrorEvent
from intune_manager.utils import get_logger


logger = get_logger(__name__)


@dataclass(slots=True)
class SyncProgressEvent:
    phase: str
    completed: int
    total: int


class SyncService:
    """Coordinate multi-service refresh cycles."""

    def __init__(
        self,
        *,
        devices: DeviceService,
        applications: ApplicationService,
        groups: GroupService,
        filters: AssignmentFilterService,
        configurations: ConfigurationService,
        audit: AuditLogService,
    ) -> None:
        self._services = {
            "devices": devices,
            "applications": applications,
            "groups": groups,
            "filters": filters,
            "configurations": configurations,
            "audit": audit,
        }
        self.progress: EventHook[SyncProgressEvent] = EventHook()
        self.errors: EventHook[ServiceErrorEvent] = EventHook()

    async def refresh_all(
        self,
        *,
        tenant_id: str | None = None,
        services: Sequence[str] | None = None,
        force: bool = False,
    ) -> None:
        target_names = list(services or self._services.keys())
        targets: Iterable[tuple[str, object]] = (
            (name, self._services[name]) for name in target_names
        )
        total = len(target_names)
        completed = 0

        for name, service in targets:
            try:
                await self._refresh_single(service, tenant_id=tenant_id, force=force)
                completed += 1
                self.progress.emit(
                    SyncProgressEvent(phase=name, completed=completed, total=total),
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Sync phase failed", phase=name)
                self.errors.emit(ServiceErrorEvent(tenant_id=tenant_id, error=exc))
                raise

    async def _refresh_single(
        self,
        service,
        *,
        tenant_id: str | None,
        force: bool,
    ) -> None:
        if isinstance(service, DeviceService):
            await service.refresh(tenant_id=tenant_id, force=force)
        elif isinstance(service, ApplicationService):
            await service.refresh(tenant_id=tenant_id, force=force)
        elif isinstance(service, GroupService):
            await service.refresh(tenant_id=tenant_id, force=force)
        elif isinstance(service, AssignmentFilterService):
            await service.refresh(tenant_id=tenant_id, force=force)
        elif isinstance(service, ConfigurationService):
            await service.refresh(tenant_id=tenant_id, force=force)
        elif isinstance(service, AuditLogService):
            await service.refresh(tenant_id=tenant_id, force=force)
        else:  # pragma: no cover - future extension
            raise TypeError(f"Unsupported service type: {service!r}")


__all__ = ["SyncService", "SyncProgressEvent"]
