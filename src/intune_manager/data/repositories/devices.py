from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta

from intune_manager.data.models import ManagedDevice
from sqlalchemy import delete

from intune_manager.data.sql import DeviceRecord
from intune_manager.data.sql.mapper import device_to_record, record_to_device

from .base import BaseCacheRepository


class DeviceRepository(BaseCacheRepository[ManagedDevice, DeviceRecord]):
    def __init__(self, db) -> None:
        super().__init__(
            db,
            resource_name="devices",
            record_model=DeviceRecord,
            default_ttl=timedelta(minutes=15),
        )

    def _to_record(self, model: ManagedDevice, tenant_id: str | None) -> DeviceRecord:
        return device_to_record(model, tenant_id=tenant_id)

    def _from_record(self, record: DeviceRecord) -> ManagedDevice:
        return record_to_device(record)

    async def replace_all_async(
        self,
        items: AsyncIterator[ManagedDevice],
        *,
        tenant_id: str | None = None,
        expires_in: timedelta | None = None,
        chunk_size: int = 250,
    ) -> int:
        """Persist devices from an async iterator without materialising the full collection."""

        now = datetime.utcnow()
        ttl = expires_in or self._default_ttl
        expires_at = now + ttl if ttl is not None else None

        with self._db.session() as session:
            stmt = delete(self._record_model)
            if self._has_tenant_column:
                stmt = stmt.where(self._record_model.tenant_id == tenant_id)
            session.exec(stmt)

            buffer: list[DeviceRecord] = []
            count = 0
            async for device in items:
                buffer.append(self._to_record(device, tenant_id))
                count += 1
                if len(buffer) >= chunk_size:
                    for record in buffer:
                        session.merge(record)
                    buffer.clear()

            if buffer:
                for record in buffer:
                    session.merge(record)

            self._update_cache_entry(session, tenant_id, count, now, expires_at)
            session.commit()
        return count


__all__ = ["DeviceRepository"]
