from __future__ import annotations

from datetime import timedelta

from intune_manager.data.models import AuditEvent
from intune_manager.data.sql import AuditEventRecord
from intune_manager.data.sql.mapper import audit_event_to_record, record_to_audit_event

from .base import BaseCacheRepository


class AuditEventRepository(BaseCacheRepository[AuditEvent, AuditEventRecord]):
    def __init__(self, db) -> None:
        super().__init__(
            db,
            resource_name="audit_events",
            record_model=AuditEventRecord,
            default_ttl=timedelta(minutes=10),
        )

    def _to_record(self, model: AuditEvent, tenant_id: str | None) -> AuditEventRecord:
        return audit_event_to_record(model, tenant_id=tenant_id)

    def _from_record(self, record: AuditEventRecord) -> AuditEvent:
        return record_to_audit_event(record)


__all__ = ["AuditEventRepository"]
