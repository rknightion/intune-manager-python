from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from intune_manager.services import ServiceRegistry


@dataclass(slots=True)
class ResourceMetric:
    key: str
    label: str
    count: int | None
    stale: bool | None
    available: bool
    warning: str | None = None


@dataclass(slots=True)
class DashboardSnapshot:
    tenant_id: str | None
    resources: List[ResourceMetric] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class DashboardController:
    """Aggregate cached resource metrics for the dashboard overview."""

    def __init__(self, services: ServiceRegistry) -> None:
        self._services = services

    # ------------------------------------------------------------------ Metrics

    def collect_snapshot(self, tenant_id: str | None = None) -> DashboardSnapshot:
        snapshot = DashboardSnapshot(tenant_id=tenant_id)

        def add_metric(
            key: str,
            label: str,
            service,
        ) -> None:
            if service is None:
                warning = f"{label} service not configured"
                snapshot.resources.append(
                    ResourceMetric(
                        key=key,
                        label=label,
                        count=None,
                        stale=None,
                        available=False,
                        warning=warning,
                    ),
                )
                snapshot.warnings.append(warning)
                return

            try:
                items = service.list_cached(tenant_id=tenant_id)
                count = len(items)
                stale = service.is_cache_stale(tenant_id=tenant_id)
                snapshot.resources.append(
                    ResourceMetric(
                        key=key,
                        label=label,
                        count=count,
                        stale=stale,
                        available=True,
                    ),
                )
                if stale:
                    snapshot.warnings.append(f"{label} cache is stale")
            except Exception as exc:  # noqa: BLE001
                warning = f"{label} unavailable: {exc}"
                snapshot.resources.append(
                    ResourceMetric(
                        key=key,
                        label=label,
                        count=None,
                        stale=None,
                        available=True,
                        warning=warning,
                    ),
                )
                snapshot.warnings.append(warning)

        add_metric("devices", "Managed devices", self._services.devices)
        add_metric("applications", "Applications", self._services.applications)
        add_metric("groups", "Groups", self._services.groups)
        add_metric("filters", "Assignment filters", self._services.assignment_filters)
        add_metric("configurations", "Configurations", self._services.configurations)
        add_metric("audit", "Audit events", self._services.audit)

        return snapshot

    # ------------------------------------------------------------------ Actions

    async def refresh_all(
        self,
        *,
        tenant_id: str | None = None,
        force: bool = True,
    ) -> None:
        if not self._services.sync:
            raise RuntimeError("Sync service not configured")
        await self._services.sync.refresh_all(tenant_id=tenant_id, force=force)


__all__ = ["DashboardController", "DashboardSnapshot", "ResourceMetric"]

