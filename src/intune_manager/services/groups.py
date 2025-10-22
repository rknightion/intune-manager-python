from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from intune_manager.data import DirectoryGroup, GroupRepository
from intune_manager.graph.client import GraphClientFactory
from intune_manager.services.base import EventHook, RefreshEvent, ServiceErrorEvent
from intune_manager.utils import get_logger


logger = get_logger(__name__)


@dataclass(slots=True)
class GroupMembershipEvent:
    group_id: str
    member_id: str
    action: str


class GroupService:
    """Manage Azure AD group metadata and membership operations."""

    def __init__(
        self,
        client_factory: GraphClientFactory,
        repository: GroupRepository,
    ) -> None:
        self._client_factory = client_factory
        self._repository = repository
        self._default_ttl = timedelta(minutes=30)

        self.refreshed: EventHook[RefreshEvent[list[DirectoryGroup]]] = EventHook()
        self.errors: EventHook[ServiceErrorEvent] = EventHook()
        self.membership: EventHook[GroupMembershipEvent] = EventHook()

    # ---------------------------------------------------------------- Queries

    def list_cached(self, tenant_id: str | None = None) -> list[DirectoryGroup]:
        groups = self._repository.list_all(tenant_id=tenant_id)
        logger.debug("Group cache read", tenant_id=tenant_id, count=len(groups))
        return groups

    def is_cache_stale(self, tenant_id: str | None = None) -> bool:
        return self._repository.is_cache_stale(tenant_id=tenant_id)

    # ---------------------------------------------------------------- Actions

    async def refresh(
        self,
        tenant_id: str | None = None,
        *,
        force: bool = False,
        include_count: bool = True,
    ) -> list[DirectoryGroup]:
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

        params = {"$count": "true"} if include_count else None
        headers = {"ConsistencyLevel": "eventual"} if include_count else None

        try:
            groups: list[DirectoryGroup] = []
            async for item in self._client_factory.iter_collection(
                "GET",
                "/groups",
                params=params,
                headers=headers,
            ):
                groups.append(DirectoryGroup.from_graph(item))

            self._repository.replace_all(
                groups,
                tenant_id=tenant_id,
                expires_in=self._default_ttl,
            )
            self.refreshed.emit(
                RefreshEvent(
                    tenant_id=tenant_id,
                    items=groups,
                    from_cache=False,
                ),
            )
            return groups
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to refresh groups", tenant_id=tenant_id)
            self.errors.emit(ServiceErrorEvent(tenant_id=tenant_id, error=exc))
            raise

    async def create_group(self, payload: dict[str, Any]) -> DirectoryGroup:
        response = await self._client_factory.request_json(
            "POST",
            "/groups",
            json_body=payload,
        )
        group = DirectoryGroup.from_graph(response)
        logger.debug("Created group", group_id=group.id)
        return group

    async def update_group(self, group_id: str, payload: dict[str, Any]) -> None:
        await self._client_factory.request(
            "PATCH",
            f"/groups/{group_id}",
            json_body=payload,
        )
        logger.debug("Updated group", group_id=group_id)

    async def delete_group(self, group_id: str) -> None:
        await self._client_factory.request("DELETE", f"/groups/{group_id}")
        logger.debug("Deleted group", group_id=group_id)

    async def add_member(self, group_id: str, member_id: str) -> None:
        body = {
            "@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{member_id}",
        }
        await self._client_factory.request(
            "POST",
            f"/groups/{group_id}/members/$ref",
            json_body=body,
        )
        self.membership.emit(
            GroupMembershipEvent(group_id=group_id, member_id=member_id, action="add"),
        )
        logger.debug("Added group member", group_id=group_id, member_id=member_id)

    async def remove_member(self, group_id: str, member_id: str) -> None:
        await self._client_factory.request(
            "DELETE",
            f"/groups/{group_id}/members/{member_id}/$ref",
        )
        self.membership.emit(
            GroupMembershipEvent(
                group_id=group_id,
                member_id=member_id,
                action="remove",
            ),
        )
        logger.debug("Removed group member", group_id=group_id, member_id=member_id)


__all__ = ["GroupService", "GroupMembershipEvent"]
