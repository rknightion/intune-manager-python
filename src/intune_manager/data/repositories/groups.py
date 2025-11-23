from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlmodel import Session, select

from intune_manager.data.models import DirectoryGroup, GroupMember
from intune_manager.data.sql import GroupMemberRecord, GroupRecord
from intune_manager.data.sql.mapper import (
    group_members_to_records,
    group_to_record,
    record_to_group,
    record_to_group_member,
)
from intune_manager.utils import get_logger

from .base import BaseCacheRepository


logger = get_logger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class GroupRepository(BaseCacheRepository[DirectoryGroup, GroupRecord]):
    def __init__(self, db) -> None:
        super().__init__(
            db,
            resource_name="groups",
            record_model=GroupRecord,
            default_ttl=timedelta(minutes=30),
        )

    def _to_record(self, model: DirectoryGroup, tenant_id: str | None) -> GroupRecord:
        return group_to_record(model, tenant_id=tenant_id)

    def _from_record(self, record: GroupRecord) -> DirectoryGroup:
        return record_to_group(record)

    # ---------------------------------------------------------- Member Management

    def cache_members(
        self,
        group_id: str,
        members: Iterable[GroupMember],
        *,
        tenant_id: str | None = None,
    ) -> None:
        """Cache members for a group, replacing any existing cached members."""
        records = group_members_to_records(
            group_id, members, tenant_id=tenant_id, is_owner=False
        )
        with self._db.session() as session:
            self._replace_member_records(session, group_id, records, is_owner=False)
            session.commit()
        logger.debug("Cached group members", group_id=group_id, count=len(records))

    def cache_owners(
        self,
        group_id: str,
        owners: Iterable[GroupMember],
        *,
        tenant_id: str | None = None,
    ) -> None:
        """Cache owners for a group, replacing any existing cached owners."""
        records = group_members_to_records(
            group_id, owners, tenant_id=tenant_id, is_owner=True
        )
        with self._db.session() as session:
            self._replace_member_records(session, group_id, records, is_owner=True)
            session.commit()
        logger.debug("Cached group owners", group_id=group_id, count=len(records))

    def get_cached_members(
        self, group_id: str, *, tenant_id: str | None = None
    ) -> list[GroupMember]:
        """Retrieve cached members for a group."""
        with self._db.session() as session:
            stmt = select(GroupMemberRecord).where(
                GroupMemberRecord.group_id == group_id,
                GroupMemberRecord.is_owner == False,  # noqa: E712
            )
            if tenant_id:
                stmt = stmt.where(GroupMemberRecord.tenant_id == tenant_id)
            records = session.exec(stmt).all()
            return [record_to_group_member(record) for record in records]

    def get_cached_owners(
        self, group_id: str, *, tenant_id: str | None = None
    ) -> list[GroupMember]:
        """Retrieve cached owners for a group."""
        with self._db.session() as session:
            stmt = select(GroupMemberRecord).where(
                GroupMemberRecord.group_id == group_id,
                GroupMemberRecord.is_owner == True,  # noqa: E712
            )
            if tenant_id:
                stmt = stmt.where(GroupMemberRecord.tenant_id == tenant_id)
            records = session.exec(stmt).all()
            return [record_to_group_member(record) for record in records]

    def is_members_stale(
        self,
        group_id: str,
        *,
        tenant_id: str | None = None,
        ttl: timedelta | None = None,
    ) -> bool:
        """Check if cached members are stale based on TTL."""
        ttl = ttl or self._default_ttl
        if ttl is None:
            return False
        with self._db.session() as session:
            stmt = select(GroupMemberRecord.updated_at).where(
                GroupMemberRecord.group_id == group_id,
                GroupMemberRecord.is_owner == False,  # noqa: E712
            )
            if tenant_id:
                stmt = stmt.where(GroupMemberRecord.tenant_id == tenant_id)
            stmt = stmt.limit(1)
            result = session.exec(stmt).first()
            if result is None:
                return True  # No cache exists
            updated_at = result.replace(tzinfo=UTC) if result.tzinfo is None else result
            return _utc_now() >= updated_at + ttl

    def is_owners_stale(
        self,
        group_id: str,
        *,
        tenant_id: str | None = None,
        ttl: timedelta | None = None,
    ) -> bool:
        """Check if cached owners are stale based on TTL."""
        ttl = ttl or self._default_ttl
        if ttl is None:
            return False
        with self._db.session() as session:
            stmt = select(GroupMemberRecord.updated_at).where(
                GroupMemberRecord.group_id == group_id,
                GroupMemberRecord.is_owner == True,  # noqa: E712
            )
            if tenant_id:
                stmt = stmt.where(GroupMemberRecord.tenant_id == tenant_id)
            stmt = stmt.limit(1)
            result = session.exec(stmt).first()
            if result is None:
                return True  # No cache exists
            updated_at = result.replace(tzinfo=UTC) if result.tzinfo is None else result
            return _utc_now() >= updated_at + ttl

    def _replace_member_records(
        self,
        session: Session,
        group_id: str,
        records: list[GroupMemberRecord],
        is_owner: bool,
    ) -> None:
        """Replace all member/owner records for a group."""
        stmt = delete(GroupMemberRecord).where(
            GroupMemberRecord.group_id == group_id,
            GroupMemberRecord.is_owner == is_owner,
        )
        session.exec(stmt)
        for record in records:
            session.merge(record)


__all__ = ["GroupRepository"]
