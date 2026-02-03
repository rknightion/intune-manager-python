from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List
from datetime import datetime

from intune_manager.config import DEFAULT_GRAPH_SCOPES, SettingsManager
from intune_manager.auth import AuthManager, auth_manager
from intune_manager.data.repositories import CacheStatus
from intune_manager.services import ServiceRegistry
from intune_manager.utils import CancellationToken


@dataclass(slots=True)
class ResourceMetric:
    key: str
    label: str
    count: int | None
    stale: bool | None
    available: bool
    last_refresh: datetime | None = None
    warning: str | None = None
    cache_status: CacheStatus | None = None


@dataclass(slots=True)
class DashboardSnapshot:
    tenant: "TenantStatus"
    resources: List[ResourceMetric] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    analytics: "AnalyticsSummary" = field(default_factory=lambda: AnalyticsSummary())


@dataclass(slots=True)
class TenantStatus:
    tenant_id: str | None
    client_id: str | None
    configured: bool
    signed_in: bool
    account_name: str | None
    account_upn: str | None
    missing_scopes: List[str] = field(default_factory=list)


@dataclass(slots=True)
class AnalyticsSummary:
    compliance: Dict[str, int] = field(default_factory=dict)
    assignment_intents: Dict[str, int] = field(default_factory=dict)


class DashboardController:
    """Aggregate cached resource metrics for the dashboard overview."""

    def __init__(
        self,
        services: ServiceRegistry,
        *,
        settings_manager: SettingsManager | None = None,
        auth: AuthManager | None = None,
    ) -> None:
        self._services = services
        self._settings_manager = settings_manager or SettingsManager()
        self._auth = auth or auth_manager

    # ------------------------------------------------------------------ Metrics

    def collect_snapshot(self, tenant_id: str | None = None) -> DashboardSnapshot:
        tenant_status = self._collect_tenant_status(tenant_id)
        if tenant_id is None:
            tenant_id = tenant_status.tenant_id
        snapshot = DashboardSnapshot(tenant=tenant_status)
        if not tenant_status.configured:
            snapshot.warnings.append("Tenant configuration incomplete.")
        if not tenant_status.signed_in:
            snapshot.warnings.append("User not signed in to Microsoft Graph.")
        if tenant_status.missing_scopes:
            missing = ", ".join(tenant_status.missing_scopes)
            snapshot.warnings.append(
                f"Missing Microsoft Graph permissions: {missing}. Grant these scopes to the Intune Manager app registration.",
            )

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
                count = None
                if hasattr(service, "count_cached"):
                    count = service.count_cached(tenant_id=tenant_id)
                else:
                    items = service.list_cached(tenant_id=tenant_id)
                    count = len(items)

                # Use cache_status() if available for richer state differentiation
                status: CacheStatus | None = None
                stale: bool | None = None
                if hasattr(service, "cache_status"):
                    status = service.cache_status(tenant_id=tenant_id)
                    # Stale means expired, not never-loaded
                    stale = status == CacheStatus.EXPIRED
                else:
                    stale = service.is_cache_stale(tenant_id=tenant_id)

                last_refresh = (
                    service.last_refresh(tenant_id=tenant_id)
                    if hasattr(service, "last_refresh")
                    else None
                )
                snapshot.resources.append(
                    ResourceMetric(
                        key=key,
                        label=label,
                        count=count,
                        stale=stale,
                        available=True,
                        last_refresh=last_refresh,
                        cache_status=status,
                    ),
                )
                # Only add warning for EXPIRED status, not NEVER_LOADED
                if status == CacheStatus.EXPIRED:
                    snapshot.warnings.append(f"{label} cache is stale")
                elif stale and status is None:
                    # Fallback for services without cache_status
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

        snapshot.analytics.compliance = self._collect_compliance_breakdown(tenant_id)
        snapshot.analytics.assignment_intents = self._collect_assignment_breakdown(
            tenant_id
        )

        return snapshot

    # ------------------------------------------------------------------ Actions

    async def refresh_all(
        self,
        *,
        tenant_id: str | None = None,
        force: bool = True,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        if not self._services.sync:
            raise RuntimeError("Sync service not configured")
        if tenant_id is None:
            tenant_id = self._settings_manager.load().tenant_id
        await self._services.sync.refresh_all(
            tenant_id=tenant_id,
            force=force,
            cancellation_token=cancellation_token,
        )

    # ----------------------------------------------------------------- Helpers

    def _collect_tenant_status(
        self, override_tenant_id: str | None = None
    ) -> TenantStatus:
        settings = self._settings_manager.load()
        user = self._auth.current_user()
        tenant_id = (
            override_tenant_id
            or settings.tenant_id
            or (user.tenant_id if user else None)
        )
        configured = settings.is_configured
        signed_in = user is not None
        configured_scopes = list(settings.configured_scopes())
        token_missing = []
        try:
            token_missing = self._auth.missing_scopes()
        except AttributeError:  # pragma: no cover - legacy auth manager without helper
            token_missing = []

        configured_missing = [
            scope for scope in DEFAULT_GRAPH_SCOPES if scope not in configured_scopes
        ]

        seen: set[str] = set()
        missing_scopes: list[str] = []
        for scope in token_missing + configured_missing:
            if scope and scope not in seen:
                seen.add(scope)
                missing_scopes.append(scope)

        status = TenantStatus(
            tenant_id=tenant_id,
            client_id=settings.client_id,
            configured=configured,
            signed_in=signed_in,
            account_name=user.display_name if signed_in else None,
            account_upn=user.username if signed_in else None,
            missing_scopes=missing_scopes,
        )

        return status

    def _collect_compliance_breakdown(self, tenant_id: str | None) -> Dict[str, int]:
        service = self._services.devices
        if service is None:
            return {}
        try:
            devices = service.list_cached(tenant_id=tenant_id)
        except Exception:  # noqa: BLE001
            return {}
        counter: Counter[str] = Counter()
        for device in devices:
            state = getattr(device, "compliance_state", None)
            if hasattr(state, "value"):
                label = state.value  # Enum-like objects
            elif isinstance(state, str) and state:
                label = state
            else:
                label = "unknown"
            counter[label] += 1
        return dict(counter)

    def _collect_assignment_breakdown(self, tenant_id: str | None) -> Dict[str, int]:
        service = self._services.applications
        if service is None:
            return {}
        try:
            apps = service.list_cached(tenant_id=tenant_id)
        except Exception:  # noqa: BLE001
            return {}
        counter: Counter[str] = Counter()
        for app in apps:
            for assignment in app.assignments or []:
                intent = assignment.intent
                if hasattr(intent, "value"):
                    label = intent.value
                elif isinstance(intent, str) and intent:
                    label = intent
                else:
                    label = "unknown"
                counter[label] += 1
        return dict(counter)


__all__ = [
    "DashboardController",
    "DashboardSnapshot",
    "ResourceMetric",
    "TenantStatus",
    "AnalyticsSummary",
]
