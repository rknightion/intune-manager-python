from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime

from intune_manager.data import DirectoryGroup, GroupMember
from intune_manager.services import GroupService, ServiceErrorEvent, ServiceRegistry
from intune_manager.services.groups import GroupMemberStream, GroupMembershipEvent
from intune_manager.utils import CancellationToken


class GroupController:
    """Bridge between the groups UI and the service layer."""

    def __init__(self, services: ServiceRegistry) -> None:
        self._services = services
        self._service: GroupService | None = services.groups
        self._subscriptions: list[Callable[[], None]] = []
        self._member_cache: dict[str, list[GroupMember]] = {}
        self._owner_cache: dict[str, list[GroupMember]] = {}
        self._member_streams: dict[str, GroupMemberStream] = {}
        self._member_freshness: dict[str, datetime] = {}
        self._owner_freshness: dict[str, datetime] = {}

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

    def member_freshness(self, group_id: str) -> datetime | None:
        return self._member_freshness.get(group_id)

    def owner_freshness(self, group_id: str) -> datetime | None:
        return self._owner_freshness.get(group_id)

    def member_stream(
        self,
        group_id: str,
        *,
        page_size: int | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> GroupMemberStream:
        if self._service is None:
            raise RuntimeError("Group service not configured")
        stream = self._service.member_stream(
            group_id,
            page_size=page_size,
            cancellation_token=cancellation_token,
        )
        self._member_streams[group_id] = stream
        return stream

    def cached_member_stream(self, group_id: str) -> GroupMemberStream | None:
        return self._member_streams.get(group_id)

    def cache_members(
        self,
        group_id: str,
        members: Iterable[GroupMember],
        *,
        append: bool = False,
    ) -> None:
        items = list(members)
        if not items and append:
            return
        if append and group_id in self._member_cache:
            self._member_cache[group_id].extend(items)
        else:
            self._member_cache[group_id] = items
        if items:
            self._member_freshness[group_id] = datetime.now(UTC)

    # ----------------------------------------------------------------- Actions

    async def refresh(
        self,
        tenant_id: str | None = None,
        *,
        force: bool = False,
        cancellation_token: CancellationToken | None = None,
    ) -> list[DirectoryGroup]:
        if self._service is None:
            raise RuntimeError("Group service not configured")
        return await self._service.refresh(
            tenant_id=tenant_id,
            force=force,
            cancellation_token=cancellation_token,
        )

    async def list_members(
        self,
        group_id: str,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> list[GroupMember]:
        if self._service is None:
            raise RuntimeError("Group service not configured")
        members = await self._service.list_members(
            group_id, cancellation_token=cancellation_token
        )
        self._member_cache[group_id] = members
        self._member_streams.pop(group_id, None)
        self._member_freshness[group_id] = datetime.now(UTC)
        return members

    async def list_owners(
        self,
        group_id: str,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> list[GroupMember]:
        if self._service is None:
            raise RuntimeError("Group service not configured")
        owners = await self._service.list_owners(
            group_id, cancellation_token=cancellation_token
        )
        self._owner_cache[group_id] = owners
        self._owner_freshness[group_id] = datetime.now(UTC)
        return owners

    async def add_member(
        self,
        group_id: str,
        member_id: str,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        if self._service is None:
            raise RuntimeError("Group service not configured")
        await self._service.add_member(
            group_id, member_id, cancellation_token=cancellation_token
        )
        self._member_cache.pop(group_id, None)
        self._member_streams.pop(group_id, None)

    async def remove_member(
        self,
        group_id: str,
        member_id: str,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        if self._service is None:
            raise RuntimeError("Group service not configured")
        await self._service.remove_member(
            group_id, member_id, cancellation_token=cancellation_token
        )
        self._member_cache.pop(group_id, None)
        self._member_streams.pop(group_id, None)

    async def delete_group(
        self,
        group_id: str,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        if self._service is None:
            raise RuntimeError("Group service not configured")
        await self._service.delete_group(
            group_id, cancellation_token=cancellation_token
        )
        self._member_cache.pop(group_id, None)
        self._owner_cache.pop(group_id, None)
        self._member_streams.pop(group_id, None)

    async def create_group(
        self,
        payload: dict[str, object],
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> DirectoryGroup:
        if self._service is None:
            raise RuntimeError("Group service not configured")
        return await self._service.create_group(
            payload, cancellation_token=cancellation_token
        )

    async def update_membership_rule(
        self,
        group_id: str,
        rule: str | None,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        if self._service is None:
            raise RuntimeError("Group service not configured")
        await self._service.update_membership_rule(
            group_id, rule, cancellation_token=cancellation_token
        )

    async def member_of_map(
        self,
        group_ids: Iterable[str],
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> dict[str, list[str]]:
        if self._service is None:
            return {}
        return await self._service.fetch_member_of_map(
            group_ids, cancellation_token=cancellation_token
        )


__all__ = ["GroupController"]
