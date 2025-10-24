from __future__ import annotations

from datetime import timedelta

from intune_manager.data import AssignmentFilter, AssignmentFilterRepository
from intune_manager.data.validation import GraphResponseValidator
from intune_manager.graph.client import GraphClientFactory
from intune_manager.graph.requests import assignment_filters_request
from intune_manager.services.base import EventHook, RefreshEvent, ServiceErrorEvent
from intune_manager.utils import CancellationError, CancellationToken, get_logger


logger = get_logger(__name__)


class AssignmentFilterService:
    """Manage Intune assignment filters cache."""

    def __init__(
        self,
        client_factory: GraphClientFactory,
        repository: AssignmentFilterRepository,
    ) -> None:
        self._client_factory = client_factory
        self._repository = repository
        self._default_ttl = timedelta(minutes=60)
        self._validator = GraphResponseValidator("assignment_filters")

        self.refreshed: EventHook[RefreshEvent[list[AssignmentFilter]]] = EventHook()
        self.errors: EventHook[ServiceErrorEvent] = EventHook()

    def list_cached(self, tenant_id: str | None = None) -> list[AssignmentFilter]:
        filters = self._repository.list_all(tenant_id=tenant_id)
        logger.debug("Assignment filters cache read", count=len(filters), tenant_id=tenant_id)
        return filters

    def is_cache_stale(self, tenant_id: str | None = None) -> bool:
        return self._repository.is_cache_stale(tenant_id=tenant_id)

    def count_cached(self, tenant_id: str | None = None) -> int:
        return self._repository.cached_count(tenant_id=tenant_id)

    async def refresh(
        self,
        tenant_id: str | None = None,
        *,
        force: bool = False,
        cancellation_token: CancellationToken | None = None,
    ) -> list[AssignmentFilter]:
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

        request = assignment_filters_request()
        try:
            filters: list[AssignmentFilter] = []
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
                model = self._validator.parse(AssignmentFilter, payload)
                if model is None:
                    invalid_count += 1
                    continue
                filters.append(model)

            if cancellation_token:
                cancellation_token.raise_if_cancelled()
            self._repository.replace_all(
                filters,
                tenant_id=tenant_id,
                expires_in=self._default_ttl,
            )
            self.refreshed.emit(
                RefreshEvent(
                    tenant_id=tenant_id,
                    items=filters,
                    from_cache=False,
                ),
            )
            if invalid_count:
                logger.warning(
                    "Assignment filter refresh skipped invalid payloads",
                    tenant_id=tenant_id,
                    invalid=invalid_count,
                )
            return filters
        except CancellationError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to refresh assignment filters", tenant_id=tenant_id)
            self.errors.emit(ServiceErrorEvent(tenant_id=tenant_id, error=exc))
            raise


__all__ = ["AssignmentFilterService"]
