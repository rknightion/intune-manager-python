# intune_manager.data.sql – AGENT Brief

## Purpose
- Define SQLModel table schemas with Graph payload denormalization for fast querying.
- Manage database connection, versioning, and async session lifecycle.
- Provide migration utilities and backward-compatible schema evolution.

## Module Structure
- **`models.py`** (or `schema.py`): SQLModel table definitions (Device, App, Group, Assignment, etc.)
- **`manager.py`**: `DatabaseManager` — engine creation, session context managers, schema versioning
- **`migrations.py`**: Schema migration helpers (SCHEMA_VERSION tracking, upgrade functions)

## Conventions
- **Backward compatibility**: Never delete columns; mark deprecated, add migration functions.
- **Denormalization**: Store raw Graph JSON payload in each record for fast ad-hoc queries + audit trail.
- **Indexing**: Create indexes on frequently-filtered fields (e.g., device `device_name`, app `display_name`).
- **Tenancy**: Support tenant-scoped caching (optional `tenant_id` column for future multi-tenant support).
- **Async sessions**: Use `DatabaseManager.session()` context manager; never leak engine/connection.
- **Schema versioning**: Bump `SCHEMA_VERSION` + document migration in `migration.txt` on any change.

## Key Patterns

### Table Definition
```python
class DeviceRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    device_id: str = Field(index=True)  # Graph @id
    device_name: str = Field(index=True)
    user_email: str | None = Field(index=True)
    compliance_state: str
    raw_payload: str  # Full Graph JSON for audit/ad-hoc queries
    last_synced_at: datetime
    __tablename__ = "devices"
```

### Session Management
```python
async with db.session() as session:
    result = await session.execute(select(DeviceRecord).where(...))
    records = result.scalars().all()
    # Auto-commit on exit
```

### Migration Example
```python
async def migrate_v1_to_v2():
    """Add new column with default, then backfill."""
    async with db.engine.begin() as conn:
        await conn.execute(
            text("ALTER TABLE devices ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        )
```

## Guidelines
- **Type hints**: All columns fully typed; use `Optional` for nullable.
- **Validation**: Implement pydantic validators in SQLModel; catch before persist.
- **Relationships**: Minimize foreign keys (prefer denormalization + IDs); use lazy loading.
- **Migrations**: Test migrations in isolation (separate test database); document rollback strategy.
- **Testing**: Unit test with in-memory SQLite; integration test with actual file database.
- **Performance**: Monitor query times; add indexes/denormalization as needed.

## Related Modules
- See `@intune_manager/data/models` for Pydantic domain models (source)
- See `@intune_manager/data/repositories` for repository usage
- See `@intune_manager/config` for database path configuration
