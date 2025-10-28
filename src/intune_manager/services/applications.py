from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from intune_manager.data import (
    AttachmentCache,
    AttachmentMetadata,
    MobileApp,
    MobileAppAssignment,
    MobileAppRepository,
)
from intune_manager.data.validation import GraphResponseValidator
from intune_manager.graph import GraphAPIError
from intune_manager.graph.client import GraphClientFactory
from intune_manager.graph.requests import (
    mobile_app_assignments_request,
    mobile_app_icon_request,
    mobile_app_install_summary_request,
)
from intune_manager.services.base import EventHook, RefreshEvent, ServiceErrorEvent
from intune_manager.utils import CancellationError, CancellationToken, get_logger


logger = get_logger(__name__)


@dataclass(slots=True)
class InstallSummaryEvent:
    app_id: str
    summary: dict[str, Any]


class ApplicationService:
    """Manage Intune mobile applications, assignments metadata, and icon cache."""

    def __init__(
        self,
        client_factory: GraphClientFactory,
        repository: MobileAppRepository,
        attachments: AttachmentCache,
    ) -> None:
        self._client_factory = client_factory
        self._repository = repository
        self._attachments = attachments
        self._default_ttl = timedelta(minutes=20)
        self._validator = GraphResponseValidator("mobile_apps")

        self.refreshed: EventHook[RefreshEvent[list[MobileApp]]] = EventHook()
        self.errors: EventHook[ServiceErrorEvent] = EventHook()
        self.install_summary: EventHook[InstallSummaryEvent] = EventHook()
        self.icon_cached: EventHook[AttachmentMetadata] = EventHook()
        self._install_summary_cache: dict[str, tuple[dict[str, Any], datetime]] = {}
        self._summary_ttl = timedelta(minutes=15)

    # ------------------------------------------------------------------ Queries

    def list_cached(self, tenant_id: str | None = None) -> list[MobileApp]:
        apps = self._repository.list_all(tenant_id=tenant_id)
        logger.debug(
            "Application cache read",
            tenant_id=tenant_id,
            count=len(apps),
        )
        return apps

    def is_cache_stale(self, tenant_id: str | None = None) -> bool:
        return self._repository.is_cache_stale(tenant_id=tenant_id)

    def count_cached(self, tenant_id: str | None = None) -> int:
        return self._repository.cached_count(tenant_id=tenant_id)

    def last_refresh(self, tenant_id: str | None = None) -> datetime | None:
        return self._repository.last_refresh(tenant_id=tenant_id)

    # ----------------------------------------------------------------- Actions

    async def refresh(
        self,
        tenant_id: str | None = None,
        *,
        force: bool = False,
        include_assignments: bool = True,
        include_categories: bool = True,
        cancellation_token: CancellationToken | None = None,
    ) -> list[MobileApp]:
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

        expands: list[str] = []
        if include_assignments:
            expands.append("assignments")
        if include_categories:
            expands.append("categories")
        params = {"$expand": ",".join(expands)} if expands else None

        try:
            apps: list[MobileApp] = []
            self._validator.reset()
            invalid_count = 0
            async for item in self._client_factory.iter_collection(
                "GET",
                "/deviceAppManagement/mobileApps",
                params=params,
                cancellation_token=cancellation_token,
            ):
                if cancellation_token:
                    cancellation_token.raise_if_cancelled()
                payload = item if isinstance(item, dict) else {"value": item}
                model = self._validator.parse(MobileApp, payload)
                if model is None:
                    invalid_count += 1
                    continue
                apps.append(model)

            if cancellation_token:
                cancellation_token.raise_if_cancelled()
            self._repository.replace_all(
                apps,
                tenant_id=tenant_id,
                expires_in=self._default_ttl,
            )
            self.refreshed.emit(
                RefreshEvent(
                    tenant_id=tenant_id,
                    items=apps,
                    from_cache=False,
                ),
            )
            if invalid_count:
                logger.warning(
                    "Application refresh skipped invalid payloads",
                    tenant_id=tenant_id,
                    invalid=invalid_count,
                )
            return apps
        except CancellationError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Failed to refresh mobile applications", tenant_id=tenant_id
            )
            self.errors.emit(ServiceErrorEvent(tenant_id=tenant_id, error=exc))
            raise

    async def fetch_install_summary(
        self,
        app_id: str,
        *,
        tenant_id: str | None = None,
        force: bool = False,
        cancellation_token: CancellationToken | None = None,
    ) -> dict[str, Any]:
        if cancellation_token:
            cancellation_token.raise_if_cancelled()
        if not force:
            cached = self._install_summary_cache.get(app_id)
            if cached:
                payload, timestamp = cached
                now = datetime.now(UTC)
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=UTC)
                if now - timestamp < self._summary_ttl:
                    self.install_summary.emit(
                        InstallSummaryEvent(app_id=app_id, summary=payload)
                    )
                    logger.debug("Install summary served from cache", app_id=app_id)
                    return payload

        request = mobile_app_install_summary_request(app_id)
        summary = await self._client_factory.request_json(
            request.method,
            request.url,
            headers=request.headers,
            api_version=request.api_version,
            cancellation_token=cancellation_token,
        )
        event = InstallSummaryEvent(app_id=app_id, summary=summary)
        self.install_summary.emit(event)
        self._install_summary_cache[app_id] = (summary, datetime.now(UTC))
        logger.debug(
            "Fetched install summary",
            app_id=app_id,
            tenant_id=tenant_id,
        )
        return summary

    async def fetch_assignments(
        self,
        app_id: str,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> list[MobileAppAssignment]:
        if cancellation_token:
            cancellation_token.raise_if_cancelled()
        request = mobile_app_assignments_request(app_id)
        assignments: list[MobileAppAssignment] = []
        async for item in self._client_factory.iter_collection(
            request.method,
            request.url,
            cancellation_token=cancellation_token,
        ):
            if cancellation_token:
                cancellation_token.raise_if_cancelled()
            assignments.append(MobileAppAssignment.from_graph(item))
        logger.debug("Fetched app assignments", app_id=app_id, count=len(assignments))
        return assignments

    async def cache_icon(
        self,
        app_id: str,
        *,
        tenant_id: str | None = None,
        size: str = "large",
        force: bool = False,
        cancellation_token: CancellationToken | None = None,
    ) -> AttachmentMetadata | None:
        if cancellation_token:
            cancellation_token.raise_if_cancelled()
        cache_key = f"{app_id}:{size}"
        if not force:
            cached = self._attachments.get(cache_key, tenant_id=tenant_id)
            if cached:
                return cached

        request = mobile_app_icon_request(app_id, size=size)  # type: ignore[arg-type]
        try:
            blob = await self._client_factory.request_bytes(
                request.method,
                request.url,
                headers=request.headers,
                api_version=request.api_version,
                cancellation_token=cancellation_token,
            )
        except CancellationError:
            raise
        except GraphAPIError as exc:
            if getattr(exc, "status_code", None) in (404, 400):
                logger.debug("App icon not available", app_id=app_id, status=exc.status_code)
                return None
            self.errors.emit(ServiceErrorEvent(tenant_id=tenant_id, error=exc))
            raise
        if cancellation_token:
            cancellation_token.raise_if_cancelled()
        metadata = self._attachments.store(
            cache_key,
            blob,
            tenant_id=tenant_id,
            category="mobile_app_icon",
        )
        self.icon_cached.emit(metadata)
        logger.debug("Cached app icon", app_id=app_id, size=len(blob))
        return metadata


__all__ = ["ApplicationService", "InstallSummaryEvent"]
