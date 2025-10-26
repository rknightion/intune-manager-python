from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from intune_manager.data import AuditEvent, AuditEventRepository
from intune_manager.data.validation import GraphResponseValidator
from intune_manager.graph.client import GraphClientFactory
from intune_manager.graph.errors import RateLimitError
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
        self._page_size = 100
        self._max_events = 600
        self._default_window = timedelta(days=7)

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
        elif self._default_window:
            window_start = datetime.now(UTC) - self._default_window
            iso_window = window_start.replace(microsecond=0).isoformat()
            params["$filter"] = f"activityDateTime ge {iso_window.replace('+00:00', 'Z')}"
        params.setdefault("$orderby", "activityDateTime desc")
        requested_top = top or self._max_events
        max_events = min(requested_top, self._max_events)
        params["$top"] = min(max_events, self._page_size)
        page_size = params["$top"]
        request = audit_events_request(params=params or None)

        try:
            events: list[AuditEvent] = []
            self._validator.reset()
            invalid_count = 0
            truncated = False
            rate_limited = False
            try:
                async for item in self._client_factory.iter_collection(
                    request.method,
                    request.url,
                    params=request.params,
                    headers=request.headers,
                    page_size=page_size,
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
                    if len(events) >= max_events:
                        truncated = True
                        break
            except RateLimitError as exc:
                if events:
                    rate_limited = True
                    logger.warning(
                        "Audit refresh hit Graph rate limit; returning partial data",
                        fetched=len(events),
                        retry_after=exc.retry_after,
                    )
                else:
                    raise

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
            if truncated:
                logger.info(
                    "Audit refresh truncated at %s events to minimise throttling",
                    max_events,
                )
            if rate_limited:
                logger.info(
                    "Audit refresh succeeded with partial data due to throttling",
                    fetched=len(events),
                )
            return events
        except CancellationError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to refresh audit events", tenant_id=tenant_id)
            self.errors.emit(ServiceErrorEvent(tenant_id=tenant_id, error=exc))
            raise


__all__ = ["AuditLogService"]
