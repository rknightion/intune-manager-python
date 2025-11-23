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
from intune_manager.utils import CancellationError, CancellationToken, get_logger


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
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        target_names = list(services or self._services.keys())
        targets: Iterable[tuple[str, object]] = (
            (name, self._services[name]) for name in target_names
        )
        total = len(target_names)
        completed = 0

        for name, service in targets:
            if cancellation_token:
                cancellation_token.raise_if_cancelled()
            logger.info(
                f"Starting sync phase: {name}",
                tenant_id=tenant_id,
                force=force,
                phase=name,
            )
            try:
                await self._refresh_single(
                    service,
                    tenant_id=tenant_id,
                    force=force,
                    cancellation_token=cancellation_token,
                )
                logger.info(
                    f"Completed sync phase: {name}",
                    tenant_id=tenant_id,
                    phase=name,
                )
            except CancellationError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.exception("Sync phase failed", phase=name)
                self.errors.emit(ServiceErrorEvent(tenant_id=tenant_id, error=exc))
            finally:
                completed += 1
                self.progress.emit(
                    SyncProgressEvent(phase=name, completed=completed, total=total),
                )

    async def _refresh_single(
        self,
        service,
        *,
        tenant_id: str | None,
        force: bool,
        cancellation_token: CancellationToken | None,
    ) -> None:
        if isinstance(service, DeviceService):
            await service.refresh(
                tenant_id=tenant_id, force=force, cancellation_token=cancellation_token
            )
        elif isinstance(service, ApplicationService):
            await service.refresh(
                tenant_id=tenant_id, force=force, cancellation_token=cancellation_token
            )
        elif isinstance(service, GroupService):
            await service.refresh(
                tenant_id=tenant_id, force=force, cancellation_token=cancellation_token
            )
            # After syncing group metadata, sync members and owners
            await self._refresh_group_memberships(
                service, tenant_id=tenant_id, cancellation_token=cancellation_token
            )
        elif isinstance(service, AssignmentFilterService):
            await service.refresh(
                tenant_id=tenant_id, force=force, cancellation_token=cancellation_token
            )
        elif isinstance(service, ConfigurationService):
            await service.refresh(
                tenant_id=tenant_id, force=force, cancellation_token=cancellation_token
            )
        elif isinstance(service, AuditLogService):
            await service.refresh(
                tenant_id=tenant_id, force=force, cancellation_token=cancellation_token
            )
        else:  # pragma: no cover - future extension
            raise TypeError(f"Unsupported service type: {service!r}")

    async def _refresh_group_memberships(
        self,
        group_service: GroupService,
        *,
        tenant_id: str | None,
        cancellation_token: CancellationToken | None,
    ) -> None:
        """Refresh members and owners for all groups."""
        groups = group_service.list_cached(tenant_id=tenant_id)
        total_groups = len(groups)
        logger.info("Starting group membership sync", total_groups=total_groups)

        for idx, group in enumerate(groups, start=1):
            if cancellation_token:
                cancellation_token.raise_if_cancelled()

            try:
                # Refresh members
                await group_service.refresh_members(
                    group.id,
                    tenant_id=tenant_id,
                    cancellation_token=cancellation_token,
                )
                # Refresh owners
                await group_service.refresh_owners(
                    group.id,
                    tenant_id=tenant_id,
                    cancellation_token=cancellation_token,
                )
                logger.debug(
                    "Synced group membership",
                    group_id=group.id,
                    group_name=group.display_name,
                    progress=f"{idx}/{total_groups}",
                )
            except CancellationError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to sync group membership",
                    group_id=group.id,
                    group_name=group.display_name,
                    error=str(exc),
                )
                # Continue with other groups even if one fails

        logger.info("Completed group membership sync", total_groups=total_groups)


__all__ = ["SyncService", "SyncProgressEvent"]
