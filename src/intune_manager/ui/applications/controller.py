from __future__ import annotations

from collections.abc import Callable
from typing import Iterable

from intune_manager.data import AttachmentMetadata, MobileApp, MobileAppAssignment
from intune_manager.services import (
    ApplicationService,
    AssignmentService,
    ServiceRegistry,
    ServiceErrorEvent,
)
from intune_manager.services.applications import InstallSummaryEvent
from intune_manager.services.assignments import AssignmentDiff
from intune_manager.utils import CancellationToken


class ApplicationController:
    """Coordinates application workflows for the UI layer."""

    def __init__(self, services: ServiceRegistry) -> None:
        self._services = services
        self._app_service: ApplicationService | None = services.applications
        self._assignment_service: AssignmentService | None = services.assignments
        self._subscriptions: list[Callable[[], None]] = []

    # ----------------------------------------------------------------- Events

    def register_callbacks(
        self,
        *,
        refreshed: Callable[[Iterable[MobileApp], bool], None] | None = None,
        error: Callable[[ServiceErrorEvent], None] | None = None,
        install_summary: Callable[[InstallSummaryEvent], None] | None = None,
        icon_cached: Callable[[AttachmentMetadata], None] | None = None,
    ) -> None:
        if self._app_service is None:
            return
        if refreshed is not None:
            self._subscriptions.append(
                self._app_service.refreshed.subscribe(
                    lambda event: refreshed(event.items, event.from_cache),
                ),
            )
        if error is not None:
            self._subscriptions.append(self._app_service.errors.subscribe(error))
        if install_summary is not None:
            self._subscriptions.append(self._app_service.install_summary.subscribe(install_summary))
        if icon_cached is not None:
            self._subscriptions.append(self._app_service.icon_cached.subscribe(icon_cached))

        if self._assignment_service is not None and error is not None:
            self._subscriptions.append(self._assignment_service.errors.subscribe(error))

    def dispose(self) -> None:
        while self._subscriptions:
            unsubscribe = self._subscriptions.pop()
            try:
                unsubscribe()
            except Exception:  # pragma: no cover - defensive cleanup
                pass

    # ----------------------------------------------------------------- Queries

    def list_cached(self, tenant_id: str | None = None) -> list[MobileApp]:
        if self._app_service is None:
            return []
        return self._app_service.list_cached(tenant_id=tenant_id)

    def is_cache_stale(self, tenant_id: str | None = None) -> bool:
        if self._app_service is None:
            return True
        return self._app_service.is_cache_stale(tenant_id=tenant_id)

    # ----------------------------------------------------------------- Actions

    async def refresh(
        self,
        tenant_id: str | None = None,
        *,
        force: bool = False,
        include_assignments: bool = True,
        cancellation_token: CancellationToken | None = None,
    ) -> list[MobileApp]:
        if self._app_service is None:
            raise RuntimeError("Application service not configured")
        return await self._app_service.refresh(
            tenant_id=tenant_id,
            force=force,
            include_assignments=include_assignments,
            cancellation_token=cancellation_token,
        )

    async def fetch_assignments(
        self,
        app_id: str,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> list[MobileAppAssignment]:
        if self._app_service is None:
            raise RuntimeError("Application service not configured")
        return await self._app_service.fetch_assignments(app_id, cancellation_token=cancellation_token)

    async def cache_icon(
        self,
        app_id: str,
        *,
        size: str = "large",
        tenant_id: str | None = None,
        force: bool = False,
        cancellation_token: CancellationToken | None = None,
    ):
        if self._app_service is None:
            raise RuntimeError("Application service not configured")
        return await self._app_service.cache_icon(
            app_id,
            tenant_id=tenant_id,
            size=size,
            force=force,
            cancellation_token=cancellation_token,
        )

    async def fetch_install_summary(
        self,
        app_id: str,
        *,
        tenant_id: str | None = None,
        force: bool = False,
        cancellation_token: CancellationToken | None = None,
    ) -> dict[str, object]:
        if self._app_service is None:
            raise RuntimeError("Application service not configured")
        return await self._app_service.fetch_install_summary(
            app_id,
            tenant_id=tenant_id,
            force=force,
            cancellation_token=cancellation_token,
        )

    def diff_assignments(
        self,
        *,
        current: Iterable[MobileAppAssignment],
        desired: Iterable[MobileAppAssignment],
    ) -> AssignmentDiff | None:
        if self._assignment_service is None:
            return None
        return self._assignment_service.diff(current=current, desired=desired)

    async def apply_diff(
        self,
        app_id: str,
        diff: AssignmentDiff,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        if self._assignment_service is None:
            raise RuntimeError("Assignment service not configured")
        await self._assignment_service.apply_diff(app_id, diff, cancellation_token=cancellation_token)

    def export_assignments(
        self,
        assignments: Iterable[MobileAppAssignment],
    ) -> list[dict]:
        if self._assignment_service is None:
            raise RuntimeError("Assignment service not configured")
        return self._assignment_service.export_assignments(assignments)


__all__ = ["ApplicationController"]
