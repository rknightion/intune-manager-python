# intune_manager.cli – AGENT Brief

## Purpose
- Provide optional command-line entry points for diagnostics, bootstrapping, and batch operations.
- Delegate all business logic to services; keep CLI commands thin wrappers around reusable components.
- Enable headless use cases (scheduled syncs, exports, diagnostics) alongside the GUI.

## Module Structure
- **`main.py`**: CLI entry point, argument parsing (argparse), command routing
- **`commands/`**: Individual command modules (e.g., `diagnose.py`, `sync.py`, `export.py`)
- Reuse services from `intune_manager.services` (no UI-specific code)

## Conventions
- **Shared config/cache**: CLI and GUI share `~/.config/IntuneManager/` and `~/.cache/IntuneManager/`.
- **No database conflicts**: Ensure CLI and GUI don't hold conflicting locks on SQLite database.
- **Exit codes**: Use standard codes (0 = success, 1 = general error, 2 = argument error).
- **Service delegation**: Never replicate service logic; instantiate and call service APIs.
- **Progress feedback**: Use simple text output for CLI (avoid GUI overlays); log to rotating file.
- **Testing**: CLI commands are testable via mocked services; avoid live Graph API in tests.

## Key Commands (Future)
- `diagnose`: Check auth, permissions, config, cache status
- `sync`: Trigger full or incremental sync (devices, apps, groups) and exit
- `export`: Export data to CSV/JSON without launching GUI
- `cache-clear`: Clear cached data (or by domain)
- `config-check`: Validate tenant/client config

## Guidelines
- **Simple output**: Use plain text + structured logging; avoid fancy progress bars (bloat).
- **Logging**: All commands log to `~/.cache/IntuneManager/logs/app.log` (shared with GUI).
- **Error handling**: Catch service exceptions, translate to user-friendly messages + exit codes.
- **Documentation**: Add command to README with examples; mention in `migration.txt` when new commands appear.
- **Thread safety**: Ensure CLI and GUI don't run simultaneously (lock check on startup).
- **Testing**: Mock services; test argument parsing, command logic, and exit codes.

## Related Modules
- See `@intune_manager/services` for command implementation patterns
- See `@intune_manager/config` for shared config/cache directory access
- See root AGENTS.md for dependency injection patterns
