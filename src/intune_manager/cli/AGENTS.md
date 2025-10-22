# intune_manager.cli – AGENT Brief

## Purpose
- Provide optional command-line entry points for diagnostics or bootstrapping (no full CLI required yet).
- Delegate business logic to services; keep CLI commands thin wrappers around reusable components.

## Guidelines
- Ensure CLI commands respect GUI state (e.g., shared config, cache) and avoid conflicting locks.
- Default to `uv run --script cli:<name>` patterns when adding new tools.
- Document new commands in README and `migration.txt` when introduced.
