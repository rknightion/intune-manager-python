from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from intune_manager.data import AuditEvent, AuditEventRepository
from intune_manager.data.validation import GraphResponseValidator
from intune_manager.graph.client import GraphClientFactory
from intune_manager.graph.requests import audit_events_request
from intune_manager.services.base import EventHook, RefreshEvent, ServiceErrorEvent
from intune_manager.utils import CancellationError, CancellationToken, get_logger


logger = get_logger(__name__)


class AuditLogService:
    """Fetch and cache Intune audit events for reporting."""

    def __init__(
        self,
        client_factory: GraphClientFactory,
        repository: AuditEventRepository,
    ) -> None:
        self._client_factory = client_factory
        self._repository = repository
        self._default_ttl = timedelta(minutes=15)
        self._validator = GraphResponseValidator("audit_events")

        self.refreshed: EventHook[RefreshEvent[list[AuditEvent]]] = EventHook()
        self.errors: EventHook[ServiceErrorEvent] = EventHook()

    def list_cached(self, tenant_id: str | None = None) -> list[AuditEvent]:
        events = self._repository.list_all(tenant_id=tenant_id)
        logger.debug("Audit cache read", tenant_id=tenant_id, count=len(events))
        return events

    def is_cache_stale(self, tenant_id: str | None = None) -> bool:
        return self._repository.is_cache_stale(tenant_id=tenant_id)

    def count_cached(self, tenant_id: str | None = None) -> int:
        return self._repository.cached_count(tenant_id=tenant_id)

    def last_refresh(self, tenant_id: str | None = None) -> datetime | None:
        return self._repository.last_refresh(tenant_id=tenant_id)

    async def refresh(
        self,
        tenant_id: str | None = None,
        *,
        force: bool = False,
        filter_expression: str | None = None,
        top: int | None = 200,
        cancellation_token: CancellationToken | None = None,
    ) -> list[AuditEvent]:
        if cancellation_token:
            cancellation_token.raise_if_cancelled()
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

        params: dict[str, Any] = {}
        if filter_expression:
            params["$filter"] = filter_expression
        if top:
            params["$top"] = top
        request = audit_events_request(params=params or None)

        try:
            events: list[AuditEvent] = []
            self._validator.reset()
            invalid_count = 0
            async for item in self._client_factory.iter_collection(
                request.method,
                request.url,
                params=request.params,
                headers=request.headers,
                api_version=request.api_version,
                cancellation_token=cancellation_token,
            ):
                if cancellation_token:
                    cancellation_token.raise_if_cancelled()
                payload = item if isinstance(item, dict) else {"value": item}
                model = self._validator.parse(AuditEvent, payload)
                if model is None:
                    invalid_count += 1
                    continue
                events.append(model)

            if cancellation_token:
                cancellation_token.raise_if_cancelled()
            self._repository.replace_all(
                events,
                tenant_id=tenant_id,
                expires_in=self._default_ttl,
            )
            self.refreshed.emit(
                RefreshEvent(
                    tenant_id=tenant_id,
                    items=events,
                    from_cache=False,
                ),
            )
            if invalid_count:
                logger.warning(
                    "Audit refresh skipped invalid payloads",
                    tenant_id=tenant_id,
                    invalid=invalid_count,
                )
            return events
        except CancellationError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to refresh audit events", tenant_id=tenant_id)
            self.errors.emit(ServiceErrorEvent(tenant_id=tenant_id, error=exc))
            raise


__all__ = ["AuditLogService"]
