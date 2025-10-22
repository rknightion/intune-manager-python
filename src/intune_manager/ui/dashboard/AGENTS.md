# Dashboard Module Agent Guide

## Purpose
- Provide an at-a-glance overview of tenant health (counts, cache freshness, auth status, quick actions).
- Trigger global refresh flows and surface warnings for missing configuration.

## Conventions
- Keep heavy data fetching async via `AsyncBridge`; do not block the UI thread.
- Use `PageScaffold` + shared components (cards, badges) for consistent styling.
- Treat `ServiceRegistry` entries as optional — degrade gracefully when services are not wired.

## Next Steps
- Add charts/visualisations (compliance trend, assignment summary) once metrics are available.
- Integrate auth status + tenant metadata once Phase 3 settings expose signals.
- Wire quick actions for launching module-specific dialogs (devices/apps) in later phases.

