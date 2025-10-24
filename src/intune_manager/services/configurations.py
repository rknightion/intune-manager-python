from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Iterable

from intune_manager.data import ConfigurationProfile, ConfigurationProfileRepository
from intune_manager.data.validation import GraphResponseValidator
from intune_manager.graph.client import GraphClientFactory
from intune_manager.graph.requests import configuration_assign_request
from intune_manager.services.base import (
    EventHook,
    MutationStatus,
    RefreshEvent,
    ServiceErrorEvent,
    run_optimistic_mutation,
)
from intune_manager.utils import CancellationError, CancellationToken, get_logger


logger = get_logger(__name__)


@dataclass(slots=True)
class ConfigurationAssignmentEvent:
    profile_id: str
    payload: dict[str, Any]
    endpoint: str
    status: MutationStatus
    error: Exception | None = None


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
        self._validator = GraphResponseValidator("configuration_profiles")

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
        return self._repository.cached_count(tenant_id=tenant_id)

    async def refresh(
        self,
        tenant_id: str | None = None,
        *,
        force: bool = False,
        include_assignments: bool = True,
        include_settings: bool = False,
        cancellation_token: CancellationToken | None = None,
    ) -> list[ConfigurationProfile]:
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
        if include_settings:
            expands.append("settings")
        params = {"$expand": ",".join(expands)} if expands else None

        endpoints = [
            "/deviceManagement/deviceConfigurations",
            "/deviceManagement/configurationPolicies",
        ]

        try:
            profiles: list[ConfigurationProfile] = []
            self._validator.reset()
            invalid_count = 0
            for endpoint in endpoints:
                api_version = "beta" if endpoint.endswith("configurationPolicies") else None
                async for item in self._client_factory.iter_collection(
                    "GET",
                    endpoint,
                    params=params,
                    api_version=api_version,
                    cancellation_token=cancellation_token,
                ):
                    if cancellation_token:
                        cancellation_token.raise_if_cancelled()
                    payload = item if isinstance(item, dict) else {"value": item}
                    model = self._validator.parse(ConfigurationProfile, payload)
                    if model is None:
                        invalid_count += 1
                        continue
                    profiles.append(model)

            if cancellation_token:
                cancellation_token.raise_if_cancelled()
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
            if invalid_count:
                logger.warning(
                    "Configuration refresh skipped invalid payloads",
                    tenant_id=tenant_id,
                    invalid=invalid_count,
                )
            return profiles
        except CancellationError:
            raise
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
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        if cancellation_token:
            cancellation_token.raise_if_cancelled()
        assignment_list = list(assignments)
        body = {"assignments": assignment_list}
        request = configuration_assign_request(
            profile_id,
            body,
            endpoint=endpoint,
        )
        def event_builder(status: MutationStatus, error: Exception | None = None) -> ConfigurationAssignmentEvent:
            return ConfigurationAssignmentEvent(
                profile_id=profile_id,
                payload=body,
                endpoint=endpoint,
                status=status,
                error=error,
            )

        async def operation() -> None:
            if cancellation_token:
                cancellation_token.raise_if_cancelled()
            await self._client_factory.request_json(
                request.method,
                request.url,
                json_body=request.body,
                headers=request.headers,
                api_version=request.api_version,
                cancellation_token=cancellation_token,
            )

        try:
            await run_optimistic_mutation(
                emitter=self.assignments,
                event_builder=event_builder,
                operation=operation,
            )
            logger.debug(
                "Configuration assigned",
                profile_id=profile_id,
                endpoint=endpoint,
                assignments=len(assignment_list),
            )
        except CancellationError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Failed to assign configuration",
                profile_id=profile_id,
                endpoint=endpoint,
            )
            self.errors.emit(ServiceErrorEvent(tenant_id=None, error=exc))
            raise


__all__ = ["ConfigurationService", "ConfigurationAssignmentEvent"]
