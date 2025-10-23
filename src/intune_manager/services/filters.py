from __future__ import annotations

from datetime import timedelta

from intune_manager.data import AssignmentFilter, AssignmentFilterRepository
from intune_manager.graph.client import GraphClientFactory
from intune_manager.graph.requests import assignment_filters_request
from intune_manager.services.base import EventHook, RefreshEvent, ServiceErrorEvent
from intune_manager.utils import get_logger


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

        self.refreshed: EventHook[RefreshEvent[list[AssignmentFilter]]] = EventHook()
        self.errors: EventHook[ServiceErrorEvent] = EventHook()

    def list_cached(self, tenant_id: str | None = None) -> list[AssignmentFilter]:
        filters = self._repository.list_all(tenant_id=tenant_id)
        logger.debug("Assignment filters cache read", count=len(filters), tenant_id=tenant_id)
        return filters

    def is_cache_stale(self, tenant_id: str | None = None) -> bool:
        return self._repository.is_cache_stale(tenant_id=tenant_id)

    def count_cached(self, tenant_id: str | None = None) -> int:
        return self._repository.count(tenant_id=tenant_id)

    async def refresh(
        self,
        tenant_id: str | None = None,
        *,
        force: bool = False,
    ) -> list[AssignmentFilter]:
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
            async for item in self._client_factory.iter_collection(
                request.method,
                request.url,
                params=request.params,
                headers=request.headers,
                api_version=request.api_version,
            ):
                filters.append(AssignmentFilter.from_graph(item))

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
            return filters
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to refresh assignment filters", tenant_id=tenant_id)
            self.errors.emit(ServiceErrorEvent(tenant_id=tenant_id, error=exc))
            raise


__all__ = ["AssignmentFilterService"]
