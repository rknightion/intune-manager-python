# intune_manager.data.repositories – AGENT Brief

## Scope
- Provide high-level data access APIs over SQLModel storage with cache awareness.
- Coordinate cache metadata (TTL, last refresh) and expose domain models to services.

## Expectations
- Use `DatabaseManager.session()` for all database access; keep transactions short.
- Always update `CacheEntry` when mutating data to keep TTL calculations accurate.
- Log noteworthy cache operations via `intune_manager.utils.get_logger` if behaviour deviates (e.g., forced refresh, TTL override).
