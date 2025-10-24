from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from intune_manager.data import AssignmentFilter, DirectoryGroup, MobileApp, MobileAppAssignment
from intune_manager.services import (
    ApplicationService,
    AssignmentFilterService,
    AssignmentImportResult,
    AssignmentImportService,
    AssignmentService,
    GroupService,
    ServiceErrorEvent,
    ServiceRegistry,
)
from intune_manager.services.assignments import AssignmentAppliedEvent, AssignmentDiff
from intune_manager.utils import CancellationToken, ProgressCallback


class AssignmentCenterController:
    """Bridge between the assignment centre UI and backing services."""

    def __init__(self, services: ServiceRegistry) -> None:
        self._services = services
        self._application_service: ApplicationService | None = services.applications
        self._assignment_service: AssignmentService | None = services.assignments
        self._group_service: GroupService | None = services.groups
        self._filter_service: AssignmentFilterService | None = services.assignment_filters
        self._import_service: AssignmentImportService | None = services.assignment_import
        self._subscriptions: list[Callable[[], None]] = []

    # ----------------------------------------------------------------- Events

    def register_callbacks(
        self,
        *,
        applied: Callable[[AssignmentAppliedEvent], None] | None = None,
        error: Callable[[ServiceErrorEvent], None] | None = None,
    ) -> None:
        if self._assignment_service is not None and applied is not None:
            self._subscriptions.append(self._assignment_service.applied.subscribe(applied))
        if error is not None:
            if self._assignment_service is not None:
                self._subscriptions.append(self._assignment_service.errors.subscribe(error))
            if self._application_service is not None:
                self._subscriptions.append(self._application_service.errors.subscribe(error))
            if self._group_service is not None:
                self._subscriptions.append(self._group_service.errors.subscribe(error))
            if self._filter_service is not None:
                self._subscriptions.append(self._filter_service.errors.subscribe(error))

    def dispose(self) -> None:
        while self._subscriptions:
            unsubscribe = self._subscriptions.pop()
            try:
                unsubscribe()
            except Exception:  # pragma: no cover - defensive cleanup
                pass

    # ----------------------------------------------------------------- Queries

    def list_apps(self, tenant_id: str | None = None) -> list[MobileApp]:
        if self._application_service is None:
            return []
        return self._application_service.list_cached(tenant_id=tenant_id)

    def list_groups(self, tenant_id: str | None = None) -> list[DirectoryGroup]:
        if self._group_service is None:
            return []
        return self._group_service.list_cached(tenant_id=tenant_id)

    def list_filters(self, tenant_id: str | None = None) -> list[AssignmentFilter]:
        if self._filter_service is None:
            return []
        return self._filter_service.list_cached(tenant_id=tenant_id)

    def is_assignment_service_available(self) -> bool:
        return self._assignment_service is not None

    # ----------------------------------------------------------------- Actions

    async def fetch_assignments(
        self,
        app_id: str,
    ) -> list[MobileAppAssignment]:
        if self._application_service is None:
            raise RuntimeError("Application service not configured")
        return await self._application_service.fetch_assignments(app_id)

    async def refresh_filters(self, *, force: bool = False) -> list[AssignmentFilter]:
        if self._filter_service is None:
            raise RuntimeError("Assignment filter service not configured")
        return await self._filter_service.refresh(force=force)

    async def refresh_groups(self, *, force: bool = False) -> list[DirectoryGroup]:
        if self._group_service is None:
            raise RuntimeError("Group service not configured")
        return await self._group_service.refresh(force=force)

    def diff_assignments(
        self,
        *,
        current: Iterable[MobileAppAssignment],
        desired: Iterable[MobileAppAssignment],
    ) -> AssignmentDiff | None:
        if self._assignment_service is None:
            return None
        return self._assignment_service.diff(current=current, desired=desired)

    async def apply_diff(self, app_id: str, diff: AssignmentDiff) -> None:
        if self._assignment_service is None:
            raise RuntimeError("Assignment service not configured")
        await self._assignment_service.apply_diff(app_id, diff)

    def export_assignments(
        self,
        assignments: Iterable[MobileAppAssignment],
    ) -> list[dict]:
        if self._assignment_service is None:
            raise RuntimeError("Assignment service not configured")
        return self._assignment_service.export_assignments(assignments)

    def parse_import_csv(
        self,
        path: Path,
        *,
        apps: Iterable[MobileApp],
        groups: Iterable[DirectoryGroup],
        progress: ProgressCallback | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> AssignmentImportResult:
        if self._import_service is None:
            raise RuntimeError("Assignment import service not configured")
        return self._import_service.parse_csv(
            path,
            apps=apps,
            groups=groups,
            progress=progress,
            cancellation_token=cancellation_token,
        )


__all__ = ["AssignmentCenterController"]
