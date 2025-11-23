from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.exc import OperationalError

from intune_manager.data.models import ManagedDevice
from intune_manager.data.sql import DeviceRecord
from intune_manager.data.sql.mapper import device_to_record, record_to_device
from intune_manager.utils import CancellationToken, get_logger

from .base import BaseCacheRepository


logger = get_logger(__name__)


class DeviceRepository(BaseCacheRepository[ManagedDevice, DeviceRecord]):
    _LOCK_RETRIES = 5
    _LOCK_BACKOFF_BASE = 0.5

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
        cancellation_token: CancellationToken | None = None,
    ) -> int:
        """Persist devices from an async iterator, retrying on transient SQLite locks."""

        now = datetime.now(UTC)
        ttl = expires_in or self._default_ttl
        expires_at = now + ttl if ttl is not None else None

        records: list[DeviceRecord] = []
        count = 0
        async for device in items:
            if cancellation_token:
                cancellation_token.raise_if_cancelled()
            records.append(self._to_record(device, tenant_id))
            count += 1

        if cancellation_token:
            cancellation_token.raise_if_cancelled()

        await self._persist_records_with_retry(
            records,
            tenant_id=tenant_id,
            count=count,
            now=now,
            expires_at=expires_at,
            chunk_size=chunk_size,
            cancellation_token=cancellation_token,
        )
        return count

    async def _persist_records_with_retry(
        self,
        records: list[DeviceRecord],
        *,
        tenant_id: str | None,
        count: int,
        now: datetime,
        expires_at: datetime | None,
        chunk_size: int,
        cancellation_token: CancellationToken | None,
    ) -> None:
        attempt = 0
        while True:
            try:
                self._persist_records(
                    records,
                    tenant_id=tenant_id,
                    count=count,
                    now=now,
                    expires_at=expires_at,
                    chunk_size=chunk_size,
                )
                return
            except OperationalError as exc:
                if not self._is_locked_error(exc):
                    raise
                attempt += 1
                if attempt >= self._LOCK_RETRIES:
                    logger.error(
                        "Database locked while persisting devices; retries exhausted",
                        tenant_id=tenant_id,
                        attempts=attempt,
                    )
                    raise
                delay = self._LOCK_BACKOFF_BASE * (2 ** (attempt - 1))
                logger.warning(
                    "Database locked while persisting devices; retrying",
                    tenant_id=tenant_id,
                    attempt=attempt,
                    delay=delay,
                )
                if cancellation_token:
                    cancellation_token.raise_if_cancelled()
                await asyncio.sleep(delay)

    def _persist_records(
        self,
        records: list[DeviceRecord],
        *,
        tenant_id: str | None,
        count: int,
        now: datetime,
        expires_at: datetime | None,
        chunk_size: int,
    ) -> None:
        with self._db.session() as session:
            chunk = max(chunk_size, 1)
            stmt = delete(self._record_model)
            if self._has_tenant_column:
                stmt = stmt.where(self._record_model.tenant_id == tenant_id)
            session.exec(stmt)

            for start in range(0, len(records), chunk):
                for record in records[start : start + chunk]:
                    session.merge(record)

            self._update_cache_entry(session, tenant_id, count, now, expires_at)
            session.commit()

    @staticmethod
    def _is_locked_error(exc: OperationalError) -> bool:
        message = str(exc).lower()
        return "database is locked" in message


__all__ = ["DeviceRepository"]
