from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, AsyncIterator, Iterable

from intune_manager.data import DirectoryGroup, GroupMember, GroupRepository
from intune_manager.data.validation import GraphResponseValidator
from intune_manager.graph.client import GraphClientFactory
from intune_manager.graph.requests import GraphRequest
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
class GroupMembershipEvent:
    group_id: str
    member_id: str
    action: str
    status: MutationStatus
    error: Exception | None = None


@dataclass(slots=True)
class GroupMemberStream:
    """Iterate group members in fixed-size pages."""

    group_id: str
    tenant_id: str | None
    iterator: AsyncIterator[dict[str, Any]]
    page_size: int
    validator: GraphResponseValidator | None = None
    cancellation_token: CancellationToken | None = None
    _exhausted: bool = False
    _loaded: int = 0

    async def next_page(self) -> list[GroupMember]:
        token = self.cancellation_token
        if token:
            token.raise_if_cancelled()
        if self._exhausted:
            return []

        page: list[GroupMember] = []
        while len(page) < self.page_size:
            if token:
                token.raise_if_cancelled()
            try:
                item = await self.iterator.__anext__()
            except StopAsyncIteration:
                self._exhausted = True
                break
            payload = item if isinstance(item, dict) else {"value": item}
            if self.validator is not None:
                member = self.validator.parse(GroupMember, payload)
                if member is None:
                    continue
            else:
                member = GroupMember.from_graph(payload)
            page.append(member)
            self._loaded += 1

        if not page:
            self._exhausted = True
        return page

    @property
    def has_more(self) -> bool:
        return not self._exhausted

    @property
    def loaded(self) -> int:
        return self._loaded


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
        self._group_validator = GraphResponseValidator("groups")
        self._member_validator = GraphResponseValidator("group_members")

        self.refreshed: EventHook[RefreshEvent[list[DirectoryGroup]]] = EventHook()
        self.errors: EventHook[ServiceErrorEvent] = EventHook()
        self.membership: EventHook[GroupMembershipEvent] = EventHook()
        self._member_default_page_size = 100

    # ---------------------------------------------------------------- Queries

    def list_cached(self, tenant_id: str | None = None) -> list[DirectoryGroup]:
        groups = self._repository.list_all(tenant_id=tenant_id)
        logger.debug("Group cache read", tenant_id=tenant_id, count=len(groups))
        return groups

    def is_cache_stale(self, tenant_id: str | None = None) -> bool:
        return self._repository.is_cache_stale(tenant_id=tenant_id)

    def count_cached(self, tenant_id: str | None = None) -> int:
        return self._repository.cached_count(tenant_id=tenant_id)

    def last_refresh(self, tenant_id: str | None = None) -> datetime | None:
        return self._repository.last_refresh(tenant_id=tenant_id)

    # ---------------------------------------------------------------- Actions

    async def refresh(
        self,
        tenant_id: str | None = None,
        *,
        force: bool = False,
        include_count: bool = True,
        cancellation_token: CancellationToken | None = None,
    ) -> list[DirectoryGroup]:
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

        params = {"$count": "true"} if include_count else None
        headers = {"ConsistencyLevel": "eventual"} if include_count else None

        try:
            groups: list[DirectoryGroup] = []
            self._group_validator.reset()
            invalid_count = 0
            async for item in self._client_factory.iter_collection(
                "GET",
                "/groups",
                params=params,
                headers=headers,
                cancellation_token=cancellation_token,
            ):
                if cancellation_token:
                    cancellation_token.raise_if_cancelled()
                payload = item if isinstance(item, dict) else {"value": item}
                model = self._group_validator.parse(DirectoryGroup, payload)
                if model is None:
                    invalid_count += 1
                    continue
                groups.append(model)

            if cancellation_token:
                cancellation_token.raise_if_cancelled()
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
            if invalid_count:
                logger.warning(
                    "Group refresh skipped invalid payloads",
                    tenant_id=tenant_id,
                    invalid=invalid_count,
                )
            return groups
        except CancellationError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to refresh groups", tenant_id=tenant_id)
            self.errors.emit(ServiceErrorEvent(tenant_id=tenant_id, error=exc))
            raise

    async def create_group(
        self,
        payload: dict[str, Any],
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> DirectoryGroup:
        if cancellation_token:
            cancellation_token.raise_if_cancelled()
        response = await self._client_factory.request_json(
            "POST",
            "/groups",
            json_body=payload,
            cancellation_token=cancellation_token,
        )
        group = DirectoryGroup.from_graph(response)
        logger.debug("Created group", group_id=group.id)
        return group

    async def update_group(
        self,
        group_id: str,
        payload: dict[str, Any],
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        if cancellation_token:
            cancellation_token.raise_if_cancelled()
        await self._client_factory.request(
            "PATCH",
            f"/groups/{group_id}",
            json_body=payload,
            cancellation_token=cancellation_token,
        )
        logger.debug("Updated group", group_id=group_id)

    async def fetch_member_of_map(
        self,
        group_ids: Iterable[str],
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> dict[str, list[str]]:
        ids = [group_id for group_id in group_ids if group_id]
        if not ids:
            return {}

        requests: list[GraphRequest] = []
        for group_id in ids:
            requests.append(
                GraphRequest(
                    method="GET",
                    url=f"/groups/{group_id}/memberOf",
                    params={
                        "$select": "id,displayName",
                    },
                    request_id=group_id,
                ),
            )

        results: dict[str, list[str]] = {group_id: [] for group_id in ids}
        chunk_size = 20

        for start in range(0, len(requests), chunk_size):
            chunk = requests[start : start + chunk_size]
            try:
                response = await self._client_factory.execute_batch(
                    chunk,
                    cancellation_token=cancellation_token,
                )
            except CancellationError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to fetch memberOf relationships", exc_info=exc)
                continue
            for entry in response.get("responses", []):
                group_id = entry.get("id")
                if not group_id or group_id not in results:
                    continue
                status = entry.get("status", 500)
                if status >= 400:
                    logger.warning(
                        "memberOf request returned failure",
                        group_id=group_id,
                        status=status,
                    )
                    continue
                body = entry.get("body") or {}
                value = body.get("value") or []
                parents: list[str] = []
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    # Filter to only include groups (not administrativeUnits or directoryRoles)
                    odata_type = item.get("@odata.type", "")
                    if odata_type != "#microsoft.graph.group":
                        continue
                    ident = item.get("id")
                    if ident:
                        parents.append(str(ident))
                results[group_id] = parents

        return results

    async def delete_group(
        self,
        group_id: str,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        if cancellation_token:
            cancellation_token.raise_if_cancelled()
        await self._client_factory.request(
            "DELETE",
            f"/groups/{group_id}",
            cancellation_token=cancellation_token,
        )
        logger.debug("Deleted group", group_id=group_id)

    async def add_member(
        self,
        group_id: str,
        member_id: str,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        body = {
            "@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{member_id}",
        }

        def event_builder(
            status: MutationStatus, error: Exception | None = None
        ) -> GroupMembershipEvent:
            return GroupMembershipEvent(
                group_id=group_id,
                member_id=member_id,
                action="add",
                status=status,
                error=error,
            )

        async def operation() -> None:
            if cancellation_token:
                cancellation_token.raise_if_cancelled()
            await self._client_factory.request(
                "POST",
                f"/groups/{group_id}/members/$ref",
                json_body=body,
                cancellation_token=cancellation_token,
            )

        if cancellation_token:
            cancellation_token.raise_if_cancelled()
        try:
            await run_optimistic_mutation(
                emitter=self.membership,
                event_builder=event_builder,
                operation=operation,
            )
            logger.debug("Added group member", group_id=group_id, member_id=member_id)
        except CancellationError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Failed to add group member",
                group_id=group_id,
                member_id=member_id,
            )
            self.errors.emit(ServiceErrorEvent(tenant_id=None, error=exc))
            raise

    async def remove_member(
        self,
        group_id: str,
        member_id: str,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        def event_builder(
            status: MutationStatus, error: Exception | None = None
        ) -> GroupMembershipEvent:
            return GroupMembershipEvent(
                group_id=group_id,
                member_id=member_id,
                action="remove",
                status=status,
                error=error,
            )

        async def operation() -> None:
            if cancellation_token:
                cancellation_token.raise_if_cancelled()
            await self._client_factory.request(
                "DELETE",
                f"/groups/{group_id}/members/{member_id}/$ref",
                cancellation_token=cancellation_token,
            )

        if cancellation_token:
            cancellation_token.raise_if_cancelled()
        try:
            await run_optimistic_mutation(
                emitter=self.membership,
                event_builder=event_builder,
                operation=operation,
            )
            logger.debug("Removed group member", group_id=group_id, member_id=member_id)
        except CancellationError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Failed to remove group member",
                group_id=group_id,
                member_id=member_id,
            )
            self.errors.emit(ServiceErrorEvent(tenant_id=None, error=exc))
            raise

    async def list_members(
        self,
        group_id: str,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> list[GroupMember]:
        stream = self.member_stream(group_id, cancellation_token=cancellation_token)
        members: list[GroupMember] = []
        while True:
            if cancellation_token:
                cancellation_token.raise_if_cancelled()
            page = await stream.next_page()
            if not page:
                break
            members.extend(page)
        logger.debug("Fetched group members", group_id=group_id, count=len(members))
        return members

    def member_stream(
        self,
        group_id: str,
        *,
        tenant_id: str | None = None,
        page_size: int | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> GroupMemberStream:
        size = page_size or self._member_default_page_size
        iterator = self._client_factory.iter_collection(
            "GET",
            f"/groups/{group_id}/members",
            params={"$select": "id,displayName,userPrincipalName,mail"},
            headers={"ConsistencyLevel": "eventual"},
            page_size=size,
            cancellation_token=cancellation_token,
        )
        self._member_validator.reset()
        return GroupMemberStream(
            group_id=group_id,
            tenant_id=tenant_id,
            iterator=iterator,
            page_size=size,
            validator=self._member_validator,
            cancellation_token=cancellation_token,
        )

    async def list_owners(
        self,
        group_id: str,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> list[GroupMember]:
        owners: list[GroupMember] = []
        self._member_validator.reset()
        async for item in self._client_factory.iter_collection(
            "GET",
            f"/groups/{group_id}/owners",
            params={"$select": "id,displayName,userPrincipalName,mail"},
            headers={"ConsistencyLevel": "eventual"},
            cancellation_token=cancellation_token,
        ):
            if cancellation_token:
                cancellation_token.raise_if_cancelled()
            payload = item if isinstance(item, dict) else {"value": item}
            owner = self._member_validator.parse(GroupMember, payload)
            if owner is None:
                continue
            owners.append(owner)
        logger.debug("Fetched group owners", group_id=group_id, count=len(owners))
        return owners

    async def refresh_members(
        self,
        group_id: str,
        *,
        tenant_id: str | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> list[GroupMember]:
        """Fetch members from Graph API and cache them."""
        members = await self.list_members(group_id, cancellation_token=cancellation_token)
        self._repository.cache_members(group_id, members, tenant_id=tenant_id)
        logger.debug(
            "Refreshed and cached group members",
            group_id=group_id,
            count=len(members),
        )
        return members

    async def refresh_owners(
        self,
        group_id: str,
        *,
        tenant_id: str | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> list[GroupMember]:
        """Fetch owners from Graph API and cache them."""
        owners = await self.list_owners(group_id, cancellation_token=cancellation_token)
        self._repository.cache_owners(group_id, owners, tenant_id=tenant_id)
        logger.debug(
            "Refreshed and cached group owners", group_id=group_id, count=len(owners)
        )
        return owners

    def get_members(
        self, group_id: str, *, tenant_id: str | None = None
    ) -> list[GroupMember]:
        """Get cached members for a group."""
        return self._repository.get_cached_members(group_id, tenant_id=tenant_id)

    def get_owners(
        self, group_id: str, *, tenant_id: str | None = None
    ) -> list[GroupMember]:
        """Get cached owners for a group."""
        return self._repository.get_cached_owners(group_id, tenant_id=tenant_id)

    async def update_membership_rule(
        self,
        group_id: str,
        rule: str | None,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        payload: dict[str, object | None] = {"membershipRule": rule}
        if rule:
            payload["membershipRuleProcessingState"] = "On"
        else:
            payload["membershipRuleProcessingState"] = "Paused"
        await self.update_group(
            group_id, payload, cancellation_token=cancellation_token
        )
        logger.debug("Updated membership rule", group_id=group_id)


__all__ = ["GroupService", "GroupMembershipEvent", "GroupMemberStream"]
