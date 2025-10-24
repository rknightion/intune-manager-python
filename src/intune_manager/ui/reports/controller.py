from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable

from intune_manager.data import AuditEvent
from intune_manager.services import (
    AuditLogService,
    ExportService,
    ServiceErrorEvent,
    ServiceRegistry,
)
from intune_manager.utils import CancellationToken


class AuditLogController:
    """Bridge between the reports UI and audit/diagnostics services."""

    def __init__(self, services: ServiceRegistry) -> None:
        self._services = services
        self._service: AuditLogService | None = services.audit
        self._export_service: ExportService | None = services.export
        self._subscriptions: list[Callable[[], None]] = []

    # ----------------------------------------------------------------- Events

    def register_callbacks(
        self,
        *,
        refreshed: Callable[[Iterable[AuditEvent], bool], None] | None = None,
        error: Callable[[ServiceErrorEvent], None] | None = None,
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

    def dispose(self) -> None:
        while self._subscriptions:
            unsubscribe = self._subscriptions.pop()
            try:
                unsubscribe()
            except Exception:  # pragma: no cover - defensive teardown
                pass

    # ----------------------------------------------------------------- Queries

    def list_cached(self, tenant_id: str | None = None) -> list[AuditEvent]:
        if self._service is None:
            return []
        return self._service.list_cached(tenant_id=tenant_id)

    def is_cache_stale(self, tenant_id: str | None = None) -> bool:
        if self._service is None:
            return True
        return self._service.is_cache_stale(tenant_id=tenant_id)

    # ---------------------------------------------------------------- Actions

    async def refresh(
        self,
        tenant_id: str | None = None,
        *,
        force: bool = False,
        filter_expression: str | None = None,
        top: int | None = 200,
        cancellation_token: CancellationToken | None = None,
    ) -> list[AuditEvent]:
        if self._service is None:
            raise RuntimeError("Audit log service is not configured")
        return await self._service.refresh(
            tenant_id=tenant_id,
            force=force,
            filter_expression=filter_expression,
            top=top,
            cancellation_token=cancellation_token,
        )

    def export_all(self, target: Path, *, tenant_id: str | None = None) -> Path:
        if self._export_service is None:
            raise RuntimeError("Export service is not configured")
        return self._export_service.export_audit_events_json(
            target, tenant_id=tenant_id
        )


__all__ = ["AuditLogController"]
