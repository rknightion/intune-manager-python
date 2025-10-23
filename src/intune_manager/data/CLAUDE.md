# intune_manager.data – AGENT Brief

## Purpose
- Own persisted models (Pydantic domain models), SQLModel table schemas, and cache management.
- Expose repository APIs for service layer to query, cache, and mutate data.
- Manage tenant-scoped SQLite persistence with versioning and migrations.

## Module Structure
- **`models/`**: Pydantic domain models (devices, apps, groups, assignments, filters, configs, audit logs)
- **`sql/`**: SQLModel table definitions, schema versioning, database session management
- **`repositories/`**: Cache-aware APIs over SQLModel tables (list, upsert, delete, TTL tracking)
- **`storage/`**: Binary attachment handling (icons, exports, logs) with disk quota enforcement

## Conventions
- **Models**: Pydantic-based with Graph API aliases; immutable where possible; use frozen=True for output models.
- **SQLModel tables**: Direct 1:1 mapping to models; denormalize Graph payloads as JSON for fast access.
- **Repositories**: Inherit `BaseCacheRepository<DomainT, RecordT>`; define domain-specific cache TTLs.
- **Sessions**: Use `DatabaseManager.session()` context manager; transactions are short and explicit.
- **Cache metadata**: Always update `CacheEntry` when writing to database to track freshness.

## Key Patterns

### Model-to-Record Mapping
1. Graph API response → Pydantic model (via `Model.model_validate(graph_payload)`)
2. Pydantic model → SQLModel record (via `Record.from_model(pydantic_model)`)
3. SQLModel record → Pydantic model (via `Record.to_model()`) for service consumption

### Cache TTLs
- `DeviceRepository`: 15 minutes (devices change frequently during compliance cycles)
- `ApplicationRepository`: 20 minutes (app catalog relatively stable)
- `GroupRepository`: 30 minutes (group membership changes less often)
- `ConfigurationRepository`: 30 minutes
- `AuditRepository`: 15 minutes (audit logs must be relatively fresh)
- `AssignmentRepository`: Dynamic (driven by app assignment updates)

### Cache Refresh Logic
- `is_cache_stale()`: Check if TTL elapsed; returns boolean
- `list_cached()`: Return in-memory cache if fresh, else fetch from Graph + update
- `refresh_*()`: Force fetch from Graph regardless of TTL; update cache

## Guidelines
- **Type hints**: All model fields must have explicit types; use Optional where nullable.
- **Validation**: Implement `@field_validator` for domain constraints (e.g., email format, date ranges).
- **Schema changes**: Bump `SCHEMA_VERSION` in `DatabaseManager` and document migration in `migration.txt`.
- **Backward compatibility**: Never delete columns; mark deprecated fields or add migration functions.
- **Audit logging**: Log all mutations (create/update/delete) with timestamps and user context.
- **Secrets**: Never store tenant ID, client ID, or tokens in database; use secure storage (keyring) or env vars.

## Related Modules
- See `@intune_manager/services` for business logic operating on these models
- See `@intune_manager/graph` for Graph API client that feeds data into repositories
- See `@intune_manager/config` for database path configuration and settings
