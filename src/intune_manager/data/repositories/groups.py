from __future__ import annotations

from datetime import timedelta

from intune_manager.data.models import DirectoryGroup
from intune_manager.data.sql import GroupRecord
from intune_manager.data.sql.mapper import group_to_record, record_to_group

from .base import BaseCacheRepository


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


__all__ = ["GroupRepository"]
