# intune_manager.utils – AGENT Brief

## Purpose
- Host shared helpers (async tools, formatting, telemetry wrappers) that do not fit domain modules.
- Provide cross-cutting utilities used by multiple packages without introducing heavy dependencies.

## Guidelines
- Keep helpers small, well-tested, and free of business logic.
- Avoid circular imports; if a utility grows complex, promote it to a dedicated module.
- Note new reusable patterns in `migration.txt` when they influence broader architecture.
