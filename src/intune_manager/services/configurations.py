from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Iterable

from intune_manager.data import ConfigurationProfile, ConfigurationProfileRepository
from intune_manager.graph.client import GraphClientFactory
from intune_manager.graph.requests import configuration_assign_request
from intune_manager.services.base import EventHook, RefreshEvent, ServiceErrorEvent
from intune_manager.utils import get_logger


logger = get_logger(__name__)


@dataclass(slots=True)
class ConfigurationAssignmentEvent:
    profile_id: str
    payload: dict[str, Any]
    endpoint: str


class ConfigurationService:
    """Manage device configuration and policy metadata."""

    def __init__(
        self,
        client_factory: GraphClientFactory,
        repository: ConfigurationProfileRepository,
    ) -> None:
        self._client_factory = client_factory
        self._repository = repository
        self._default_ttl = timedelta(minutes=30)

        self.refreshed: EventHook[RefreshEvent[list[ConfigurationProfile]]] = EventHook()
        self.errors: EventHook[ServiceErrorEvent] = EventHook()
        self.assignments: EventHook[ConfigurationAssignmentEvent] = EventHook()

    def list_cached(self, tenant_id: str | None = None) -> list[ConfigurationProfile]:
        profiles = self._repository.list_all(tenant_id=tenant_id)
        logger.debug("Configuration cache read", tenant_id=tenant_id, count=len(profiles))
        return profiles

    def is_cache_stale(self, tenant_id: str | None = None) -> bool:
        return self._repository.is_cache_stale(tenant_id=tenant_id)

    def count_cached(self, tenant_id: str | None = None) -> int:
        return self._repository.count(tenant_id=tenant_id)

    async def refresh(
        self,
        tenant_id: str | None = None,
        *,
        force: bool = False,
        include_assignments: bool = True,
        include_settings: bool = False,
    ) -> list[ConfigurationProfile]:
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
        if include_settings:
            expands.append("settings")
        params = {"$expand": ",".join(expands)} if expands else None

        endpoints = [
            "/deviceManagement/deviceConfigurations",
            "/deviceManagement/configurationPolicies",
        ]

        try:
            profiles: list[ConfigurationProfile] = []
            for endpoint in endpoints:
                api_version = "beta" if endpoint.endswith("configurationPolicies") else None
                async for item in self._client_factory.iter_collection(
                    "GET",
                    endpoint,
                    params=params,
                    api_version=api_version,
                ):
                    profiles.append(ConfigurationProfile.from_graph(item))

            self._repository.replace_all(
                profiles,
                tenant_id=tenant_id,
                expires_in=self._default_ttl,
            )
            self.refreshed.emit(
                RefreshEvent(
                    tenant_id=tenant_id,
                    items=profiles,
                    from_cache=False,
                ),
            )
            return profiles
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to refresh configuration profiles", tenant_id=tenant_id)
            self.errors.emit(ServiceErrorEvent(tenant_id=tenant_id, error=exc))
            raise

    async def assign_profile(
        self,
        profile_id: str,
        assignments: Iterable[dict[str, Any]],
        *,
        endpoint: str = "deviceConfigurations",
    ) -> None:
        body = {"assignments": list(assignments)}
        request = configuration_assign_request(
            profile_id,
            body,
            endpoint=endpoint,
        )
        await self._client_factory.request_json(
            request.method,
            request.url,
            json_body=request.body,
            headers=request.headers,
            api_version=request.api_version,
        )
        logger.debug(
            "Configuration assigned",
            profile_id=profile_id,
            endpoint=endpoint,
            assignments=len(body["assignments"]),
        )
        self.assignments.emit(
            ConfigurationAssignmentEvent(
                profile_id=profile_id,
                payload=body,
                endpoint=endpoint,
            ),
        )


__all__ = ["ConfigurationService", "ConfigurationAssignmentEvent"]
