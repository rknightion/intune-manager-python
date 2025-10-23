# intune_manager.data.repositories – AGENT Brief

## Purpose
- Provide high-level, cache-aware data access APIs over SQLModel persistence.
- Coordinate cache metadata (TTL, last refresh time) and expose domain models to services.
- Implement generic cache patterns (BaseCacheRepository) with domain-specific TTLs and fetch logic.

## Module Structure
- **`base.py`**: `BaseCacheRepository<DomainT, RecordT>` — generic cache-aware base with TTL tracking
- **`device_repository.py`**: Device-specific repository (TTL: 15m), sync methods
- **`application_repository.py`**: App-specific repository (TTL: 20m), icon caching coordination
- **`group_repository.py`**: Group-specific repository (TTL: 30m), membership tracking
- **`assignment_repository.py`**: Assignment repository with join management
- **`filter_repository.py`**: Filter repository (TTL: 60m)
- **`configuration_repository.py`**: Configuration profile repository (TTL: 30m)
- **`audit_repository.py`**: Audit log repository (TTL: 15m)

## Conventions
- **Transactions**: Use `DatabaseManager.session()` context manager; keep transactions short.
- **Cache metadata**: Always update `CacheEntry` when writing/replacing data (bump `last_synced_at`).
- **TTL checking**: Implement `is_cache_stale()` to check TTL; use in `list_cached()` logic.
- **Graph integration**: Repositories receive Pydantic models from Graph layer; persist as SQLModel records.
- **Optional caching**: Services can force-refresh (ignore TTL) on user action; repositories support both.
- **Error propagation**: Raise domain-specific exceptions; let services handle retry/backoff.

## Key Patterns

### Cache-Aware List
```python
async def list_cached(self) -> list[DomainT]:
    if not self.is_cache_stale():
        return self._in_memory_cache
    # Fetch from Graph, update cache + TTL
    records = await self._fetch_from_graph()
    self._update_cache(records)
    return records
```

### Upsert with TTL Update
```python
async def replace_all(self, models: list[DomainT]) -> None:
    records = [Record.from_model(m) for m in models]
    async with self._db.session() as session:
        await session.delete(...)  # Clear old
        session.add_all(records)
        await session.commit()
        # Update CacheEntry
        await self._update_cache_entry(len(records))
```

### Repository Initialization
```python
class DeviceRepository(BaseCacheRepository[ManagedDevice, DeviceRecord]):
    CACHE_TTL = timedelta(minutes=15)

    async def _fetch_from_graph(self) -> list[ManagedDevice]:
        # Use graph client to fetch
```

## Guidelines
- **Type hints**: All methods return fully typed `list[DomainT]` or `DomainT | None`.
- **Async-first**: All I/O (Graph, database) is async; never block.
- **Logging**: Log cache hits/misses, TTL overrides, mutation counts; use structured logging.
- **Testing**: Unit test with in-memory SQLite; mock Graph layer for isolation.
- **Schema bumps**: When SQLModel schema changes, bump `SCHEMA_VERSION` + document migration.

## Related Modules
- See `@intune_manager/data/models` for Pydantic domain models
- See `@intune_manager/data/sql` for SQLModel schema + session management
- See `@intune_manager/services` for service-level repository usage
