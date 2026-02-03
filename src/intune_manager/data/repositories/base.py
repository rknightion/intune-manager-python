from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Generic, Sequence, TypeVar

from sqlalchemy import delete, func
from sqlmodel import SQLModel, Session, select

from intune_manager.data.sql import CacheEntry, DatabaseManager
from intune_manager.utils import get_logger


DomainT = TypeVar("DomainT")
RecordT = TypeVar("RecordT", bound=SQLModel)

logger = get_logger(__name__)

DEFAULT_SCOPE = "__global__"


class CacheStatus(str, Enum):
    """Represents the status of a cache entry.

    - NEVER_LOADED: No cache entry exists (first startup, never synced)
    - FRESH: Cache entry exists and TTL has not expired
    - EXPIRED: Cache entry exists but TTL has expired
    """

    NEVER_LOADED = "never_loaded"
    FRESH = "fresh"
    EXPIRED = "expired"


def _utc_now() -> datetime:
    return datetime.now(UTC)


class BaseCacheRepository(Generic[DomainT, RecordT]):
    """Shared cache-aware repository utilities."""

    def __init__(
        self,
        db: DatabaseManager,
        *,
        resource_name: str,
        record_model: type[RecordT],
        default_ttl: timedelta | None = None,
    ) -> None:
        self._db = db
        self._resource = resource_name
        self._record_model = record_model
        self._default_ttl = default_ttl
        self._has_tenant_column = hasattr(record_model, "tenant_id")

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    # ----------------------------------------------------------------- Public

    def replace_all(
        self,
        items: Iterable[DomainT],
        *,
        tenant_id: str | None = None,
        expires_in: timedelta | None = None,
    ) -> None:
        models = list(items)
        records = [self._to_record(model, tenant_id) for model in models]
        now = _utc_now()
        ttl = expires_in or self._default_ttl
        expires_at = now + ttl if ttl is not None else None

        with self._db.session() as session:
            self._replace_records(session, records, tenant_id)
            self._post_replace(session, models, tenant_id)
            self._update_cache_entry(session, tenant_id, len(records), now, expires_at)
            session.commit()

    def list_all(self, *, tenant_id: str | None = None) -> list[DomainT]:
        with self._db.session() as session:
            records = session.exec(self._select_records(tenant_id)).all()
            return [self._from_record(record) for record in records]

    def get(self, item_id: str, *, tenant_id: str | None = None) -> DomainT | None:
        with self._db.session() as session:
            stmt = self._select_records(tenant_id).where(
                self._record_model.id == item_id
            )
            record = session.exec(stmt).one_or_none()
            return self._from_record(record) if record else None

    def count(self, *, tenant_id: str | None = None) -> int:
        with self._db.session() as session:
            stmt = select(func.count(self._record_model.id))
            if self._has_tenant_column:
                stmt = stmt.where(self._record_model.tenant_id == tenant_id)
            return session.exec(stmt).one()

    def cached_count(
        self,
        *,
        tenant_id: str | None = None,
        fallback: bool = True,
    ) -> int:
        entry = self.cache_entry(tenant_id=tenant_id)
        if entry and entry.item_count is not None:
            return entry.item_count
        if not fallback:
            return 0
        computed = self.count(tenant_id=tenant_id)
        with self._db.session() as session:
            scoped = session.get(CacheEntry, (self._resource, self._scope(tenant_id)))
            if scoped is not None:
                scoped.item_count = computed
                session.add(scoped)
                session.commit()
        return computed

    def clear(self, *, tenant_id: str | None = None) -> None:
        with self._db.session() as session:
            self._replace_records(session, [], tenant_id)
            self._remove_cache_entry(session, tenant_id)
            session.commit()

    def cache_entry(self, *, tenant_id: str | None = None) -> CacheEntry | None:
        with self._db.session() as session:
            entry = session.get(CacheEntry, (self._resource, self._scope(tenant_id)))
            if entry is not None:
                entry.last_refresh = self._as_utc(entry.last_refresh)
                entry.expires_at = self._as_utc(entry.expires_at)
            return entry

    def last_refresh(self, *, tenant_id: str | None = None) -> datetime | None:
        entry = self.cache_entry(tenant_id=tenant_id)
        return self._as_utc(entry.last_refresh) if entry is not None else None

    def is_cache_stale(
        self, *, tenant_id: str | None = None, now: datetime | None = None
    ) -> bool:
        entry = self.cache_entry(tenant_id=tenant_id)
        if entry is None or entry.last_refresh is None:
            return True
        if entry.expires_at is None:
            return False
        current = self._as_utc(now if now is not None else _utc_now())
        expires_at = self._as_utc(entry.expires_at)
        assert expires_at is not None  # guarded by earlier check
        return current >= expires_at

    def cache_status(
        self, *, tenant_id: str | None = None, now: datetime | None = None
    ) -> CacheStatus:
        """Return the cache status differentiating never-loaded from expired.

        Returns:
            CacheStatus.NEVER_LOADED: No cache entry exists (first startup)
            CacheStatus.FRESH: Cache entry exists and TTL has not expired
            CacheStatus.EXPIRED: Cache entry exists but TTL has expired
        """
        entry = self.cache_entry(tenant_id=tenant_id)
        if entry is None or entry.last_refresh is None:
            return CacheStatus.NEVER_LOADED
        if entry.expires_at is None:
            return CacheStatus.FRESH
        current = self._as_utc(now if now is not None else _utc_now())
        expires_at = self._as_utc(entry.expires_at)
        assert expires_at is not None  # guarded by earlier check
        if current >= expires_at:
            return CacheStatus.EXPIRED
        return CacheStatus.FRESH

    # --------------------------------------------------------------- Internals

    def _replace_records(
        self,
        session: Session,
        records: Sequence[RecordT],
        tenant_id: str | None,
    ) -> None:
        stmt = delete(self._record_model)
        if self._has_tenant_column:
            stmt = stmt.where(self._record_model.tenant_id == tenant_id)
        session.exec(stmt)
        for record in records:
            session.merge(record)

    def _post_replace(
        self,
        session: Session,
        models: Sequence[DomainT],
        tenant_id: str | None,
    ) -> None:  # pragma: no cover - default hook
        return None

    def _update_cache_entry(
        self,
        session: Session,
        tenant_id: str | None,
        item_count: int,
        last_refresh: datetime,
        expires_at: datetime | None,
    ) -> None:
        scope = self._scope(tenant_id)
        entry = session.get(CacheEntry, (self._resource, scope))
        if entry is None:
            entry = CacheEntry(
                resource=self._resource,
                scope=scope,
                tenant_id=tenant_id,
            )
            session.add(entry)
        entry.tenant_id = tenant_id
        entry.last_refresh = self._as_utc(last_refresh)
        entry.expires_at = self._as_utc(expires_at)
        entry.item_count = item_count

    def _remove_cache_entry(self, session: Session, tenant_id: str | None) -> None:
        scope = self._scope(tenant_id)
        entry = session.get(CacheEntry, (self._resource, scope))
        if entry is not None:
            session.delete(entry)

    def _select_records(self, tenant_id: str | None):
        stmt = select(self._record_model)
        if self._has_tenant_column:
            stmt = stmt.where(self._record_model.tenant_id == tenant_id)
        return stmt

    def _scope(self, tenant_id: str | None) -> str:
        return tenant_id or DEFAULT_SCOPE

    # ------------------------------------------------------------ Abstractions

    def _to_record(self, model: DomainT, tenant_id: str | None) -> RecordT:
        raise NotImplementedError

    def _from_record(self, record: RecordT) -> DomainT:
        raise NotImplementedError


__all__ = ["BaseCacheRepository", "CacheStatus"]
