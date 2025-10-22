# Devices Module Agent Guide

## Purpose
- Provide a responsive managed device explorer with search, filtering, and actionable insights.
- Surface device metadata, installed apps, and management actions in a single pane of glass.
- Bridge `DeviceService` events into the UI while keeping long-running Graph calls off the UI thread.

## Conventions
- Use `DeviceController` for all service interactions; never call `DeviceService` directly from widgets.
- Keep models (`QAbstractTableModel` + `QSortFilterProxyModel`) focused on data projection; avoid business logic in views.
- Update UI state via `UIContext` helpers (`set_busy`, `show_notification`, `show_banner`) for consistent feedback.
- Handle missing services gracefully by disabling actions and presenting guidance copy.
- Ensure refresh/action flows emit optimistic UI updates and reconcile with service callbacks.

## Next Steps
- Add inline compliance badges and custom delegates if UX polish requires richer table cells.
- Extend detail pane with timeline/history once telemetry events arrive in Phase 7.
- Wire bulk actions (multi-select + batch execution) after assignment centers are implemented.

