# Applications Module Agent Guide

## Purpose
- Provide a searchable, filterable catalog of Intune managed applications with platform-aware metadata.
- Surface rich detail per application (metadata, assignments, install summary, cached icons).
- Enable single-app and bulk assignment workflows via `AssignmentController`.
- Deliver fast, responsive UX via smart caching and incremental rendering.

## Module Structure
- **`controller.py`**: `ApplicationController` — service orchestration, async operations, signal emission
- **`models.py`**: PySide6 models (`ApplicationTableModel`, `QSortFilterProxyModel`)
- **`widgets.py`**: Main UI components (`ApplicationBrowserWidget`, `ApplicationDetailDrawer`, `AssignmentEditor`)
- **`bulk_assignment.py`**: `BulkAssignmentDialog` — guided workflow for multi-app assignments
- **`assignment_editor.py`**: Single-app assignment editing with diff/apply flows

## Conventions
- **Service routing**: All Graph/service calls go through `ApplicationController`; widgets remain declarative.
- **Icon caching**: Request icons via `ApplicationService.cache_icon()`; reuse from cache on subsequent renders; never block UI thread.
- **Assignment workflows**: Route single-app edits through `AssignmentEditor`; multi-app through `BulkAssignmentDialog` (in `bulk_assignment.py`).
- **State sync**: Reflect async operation state in UI via `UIContext` helpers (`set_busy()`, `show_notification()`).
- **Incremental refresh**: Cache app list + icons; diff updates on refresh instead of full reload.
- **Service optionality**: Guard all `AssignmentService` calls; disable assignment affordances if service unavailable.

## Key Patterns

### Bulk Assignment Workflow
The `BulkAssignmentDialog` (in `bulk_assignment.py`) provides a step-by-step guided experience:
1. **Select apps**: User checks apps from the current list
2. **Select groups**: User picks target groups with optional filter
3. **Set intent**: Choose Available, Required, or Uninstall
4. **Preview**: `AssignmentService.diff()` shows creates/updates/deletes before execution
5. **Apply**: User confirms; `AssignmentService.apply()` executes against Graph and updates cache
6. **History**: Workflow appends to audit trail for observability

### Caching Strategy
- `ApplicationTableModel` holds in-memory app list; refresh triggers full reload + diff
- Icons fetched via `ApplicationService.cache_icon()` — stored in `storage/` with LRU eviction
- Assignment list per app cached in detail drawer; refresh on user action or stale signal

### Error Handling
- Graph API errors surface in notification bar with retry option
- Validation errors (e.g., no groups selected) prevent dialog advance with clear guidance
- Permission errors (missing Graph scopes) disable bulk assignment UI

## Guidelines
- **Responsiveness**: Keep main grid interactive; use `AsyncBridge` for all Graph/DB calls.
- **Icon optimization**: Pre-fetch icons in background; lazy-load details on user expand.
- **Accessibility**: Keyboard navigation (Tab/Enter), clear labels, screen reader hints.
- **Testing**: Unit test models; integration test controller with mocked services.
- **Cross-module**: Coordinate with `AssignmentService` for assignment validation; respect cache freshness signals.

## Related Modules
- See `@intune_manager/services` for `ApplicationService` and `AssignmentService`
- See `@intune_manager/ui/components` for shared widgets and dialogs
- See `@intune_manager/ui/assignments` for bulk assignment workspace (if cross-linking needed)
