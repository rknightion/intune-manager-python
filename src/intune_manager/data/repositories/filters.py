from __future__ import annotations

from datetime import timedelta

from intune_manager.data.models import AssignmentFilter
from intune_manager.data.sql import AssignmentFilterRecord
from intune_manager.data.sql.mapper import (
    assignment_filter_to_record,
    record_to_assignment_filter,
)

from .base import BaseCacheRepository


class AssignmentFilterRepository(
    BaseCacheRepository[AssignmentFilter, AssignmentFilterRecord],
):
    def __init__(self, db) -> None:
        super().__init__(
            db,
            resource_name="assignment_filters",
            record_model=AssignmentFilterRecord,
            default_ttl=timedelta(minutes=30),
        )

    def _to_record(
        self,
        model: AssignmentFilter,
        tenant_id: str | None,
    ) -> AssignmentFilterRecord:
        return assignment_filter_to_record(model, tenant_id=tenant_id)

    def _from_record(self, record: AssignmentFilterRecord) -> AssignmentFilter:
        return record_to_assignment_filter(record)


__all__ = ["AssignmentFilterRepository"]
