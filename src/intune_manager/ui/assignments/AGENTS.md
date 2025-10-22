# Assignments Module Agent Guide

## Purpose
- Provide a workspace to compare, back up, and orchestrate bulk assignment changes across Intune applications.
- Surface diffs before execution with clear conflict warnings (filters, missing groups) and capture an audit-friendly history trail.
- Act as the coordination point for upcoming bulk device actions and group-driven assignment scenarios.

## Conventions
- Route all Graph/service access through `AssignmentCenterController`; the widget layer should stay declarative and async-safe.
- Treat all service dependencies (`applications`, `assignments`, `groups`, `assignment_filters`) as optional; downgrade UI affordances when unavailable.
- Strip assignment IDs when cloning between apps so that `AssignmentService.diff` can compute create/update sets correctly.
- Keep the dry-run preview fast: reuse cached assignments and fall back to on-demand fetches when caches miss.
- Append user-visible history entries for every preview/apply/export to aid observability across sessions.

## Next Steps
- Extend previews with side-by-side visualisation of setting payload differences once advanced assignment settings land (see P6.5.0).
- Integrate telemetry hooks so command palette and dashboard analytics can surface assignment activity (planned Phase 7 work).
- Add pytest-qt coverage for the wizard flow (source select → preview → apply) when the UI test suite is introduced in Phase 8.

