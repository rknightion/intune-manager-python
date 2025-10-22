# Applications Module Agent Guide

## Purpose
- Provide a searchable catalog of Intune managed applications with platform filtering and assignment insights.
- Surface rich detail per application (metadata, assignments, install summary, cached icons).
- Enable assignment diff/apply workflows using `AssignmentService` while offering quick export/backup tooling.

## Conventions
- Route Graph/service interactions through `ApplicationController`; widgets must stay declarative.
- Cache icons via `ApplicationService.cache_icon` and reuse on subsequent renders; avoid blocking the UI.
- Keep assignment editing in a dedicated drawer/dialog to prevent cluttering the main grid.
- Optimise for incremental refreshes — reuse cached data when possible and reflect stale states via `UIContext`.
- Treat `AssignmentService` as optional; guard UI affordances if the service is unavailable.

## Next Steps
- Expand assignment editor to support create/delete of targets and richer settings validation.
- Introduce bulk operations (multi-select apply/export) once Phase 6.7 assignment centre is complete.
- Add lazy loading for install summaries to avoid redundant Graph calls.

