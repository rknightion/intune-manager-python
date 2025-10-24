# Reports Module Agent Guide

## Purpose
- Surface Intune audit events collected via Microsoft Graph alongside local diagnostic logs.
- Provide filtering, search, and export affordances for compliance and troubleshooting workflows.
- Bridge UI actions to `AuditLogService`, `ExportService`, and `DiagnosticsService` without embedding service logic in widgets.

## Module Structure
- **`controller.py`**: `AuditLogController` – wires service events, manages refresh/export operations.
- **`models.py`**: Table + proxy models for audit events (`AuditEventTableModel`, `AuditEventFilterProxyModel`).
- **`widgets.py`**: `ReportsWidget` page (audit event grid, detail pane, diagnostics tab) + supporting detail widgets.

## Conventions
- **Async boundaries**: Delegate async work to controller/service; trigger via `UIContext.run_async`.
- **Error handling**: Use `describe_exception()` helper to classify transient errors; surface via `InlineStatusMessage` and notifications.
- **Filtering**: Keep `QSortFilterProxyModel` lightweight (string comparisons only); Graph filtering handled in controller refresh params.
- **Exports**: Route all file writes through services (`ExportService` for audit JSON, `DiagnosticsService` for log bundles).
- **Degradation**: If services are unavailable, disable actions and render inline guidance (no crashes).

## Related Modules
- `@intune_manager/services/audit` – refresh and caching pipeline for audit events.
- `@intune_manager/services/export` – JSON export helpers for cached data sets.
- `@intune_manager/services/diagnostics` – local log bundle inspection/export.
