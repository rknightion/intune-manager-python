# intune_manager.data.sql – AGENT Brief

## Scope
- Manage SQLModel schema definitions, migrations, and database connections.
- Provide session utilities and helpers for repositories to interact with SQLite caches.

## Expectations
- Keep schema changes backward compatible; bump `SCHEMA_VERSION` and document migrations in `migration.txt`.
- Store raw Graph payloads alongside indexed columns for fast filtering.
- Expose context managers for read/write sessions; avoid leaking engines outside this module.
