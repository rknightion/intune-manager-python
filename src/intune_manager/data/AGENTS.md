# intune_manager.data – AGENT Brief

## Purpose
- Own persisted models, SQLModel table declarations, migrations, and caching utilities.
- Expose repository primitives used by service layer and background sync tasks.

## Guidelines
- Keep models pydantic/SQLModel-based with explicit type hints and validation helpers.
- Centralize session management and avoid direct database access from UI modules.
- Document schema changes in `migration.txt` (Phase 4 tasks) with migration strategy notes.
