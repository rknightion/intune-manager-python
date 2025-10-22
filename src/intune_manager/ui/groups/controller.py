from __future__ import annotations

from collections.abc import Callable
from typing import Iterable

from intune_manager.data import DirectoryGroup, GroupMember
from intune_manager.services import GroupService, ServiceErrorEvent, ServiceRegistry
from intune_manager.services.groups import GroupMembershipEvent


class GroupController:
    """Bridge between the groups UI and the service layer."""

    def __init__(self, services: ServiceRegistry) -> None:
        self._services = services
        self._service: GroupService | None = services.groups
        self._subscriptions: list[Callable[[], None]] = []
        self._member_cache: dict[str, list[GroupMember]] = {}
        self._owner_cache: dict[str, list[GroupMember]] = {}

    def register_callbacks(
        self,
        *,
        refreshed: Callable[[Iterable[DirectoryGroup], bool], None] | None = None,
        error: Callable[[ServiceErrorEvent], None] | None = None,
        membership: Callable[[GroupMembershipEvent], None] | None = None,
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
        if membership is not None:
            self._subscriptions.append(self._service.membership.subscribe(membership))

    def dispose(self) -> None:
        while self._subscriptions:
            unsubscribe = self._subscriptions.pop()
            try:
                unsubscribe()
            except Exception:  # pragma: no cover - best effort cleanup
                pass

    # ----------------------------------------------------------------- Queries

    def list_cached(self, tenant_id: str | None = None) -> list[DirectoryGroup]:
        if self._service is None:
            return []
        return self._service.list_cached(tenant_id=tenant_id)

    def is_cache_stale(self, tenant_id: str | None = None) -> bool:
        if self._service is None:
            return True
        return self._service.is_cache_stale(tenant_id=tenant_id)

    def cached_members(self, group_id: str) -> list[GroupMember] | None:
        return self._member_cache.get(group_id)

    def cached_owners(self, group_id: str) -> list[GroupMember] | None:
        return self._owner_cache.get(group_id)

    # ----------------------------------------------------------------- Actions

    async def refresh(
        self,
        tenant_id: str | None = None,
        *,
        force: bool = False,
    ) -> list[DirectoryGroup]:
        if self._service is None:
            raise RuntimeError("Group service not configured")
        return await self._service.refresh(tenant_id=tenant_id, force=force)

    async def list_members(self, group_id: str) -> list[GroupMember]:
        if self._service is None:
            raise RuntimeError("Group service not configured")
        members = await self._service.list_members(group_id)
        self._member_cache[group_id] = members
        return members

    async def list_owners(self, group_id: str) -> list[GroupMember]:
        if self._service is None:
            raise RuntimeError("Group service not configured")
        owners = await self._service.list_owners(group_id)
        self._owner_cache[group_id] = owners
        return owners

    async def add_member(self, group_id: str, member_id: str) -> None:
        if self._service is None:
            raise RuntimeError("Group service not configured")
        await self._service.add_member(group_id, member_id)
        self._member_cache.pop(group_id, None)

    async def remove_member(self, group_id: str, member_id: str) -> None:
        if self._service is None:
            raise RuntimeError("Group service not configured")
        await self._service.remove_member(group_id, member_id)
        self._member_cache.pop(group_id, None)

    async def delete_group(self, group_id: str) -> None:
        if self._service is None:
            raise RuntimeError("Group service not configured")
        await self._service.delete_group(group_id)
        self._member_cache.pop(group_id, None)
        self._owner_cache.pop(group_id, None)

    async def create_group(self, payload: dict[str, object]) -> DirectoryGroup:
        if self._service is None:
            raise RuntimeError("Group service not configured")
        return await self._service.create_group(payload)

    async def update_membership_rule(self, group_id: str, rule: str | None) -> None:
        if self._service is None:
            raise RuntimeError("Group service not configured")
        await self._service.update_membership_rule(group_id, rule)


__all__ = ["GroupController"]
