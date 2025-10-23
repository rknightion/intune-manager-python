# Assignments Module Agent Guide

## Purpose
- Provide a centralized workspace for managing bulk application assignments across groups and filters.
- Compare existing vs. proposed assignments with detailed diff (creates, updates, deletes) before execution.
- Support multi-app assignment workflows with dry-run preview, rollback history, and audit trail.
- Integrate with device compliance targeting and filter-based assignment scenarios.

## Module Structure
- **`controller.py`**: `AssignmentCenterController` — service orchestration, diff computation, apply orchestration
- **`models.py`**: Assignment diff models, history entry serialization, audit event structures
- **`widgets.py`**: Workspace layout (left: app/group selector, center: diff preview, right: action panel)

## Conventions
- **Service routing**: Route all `AssignmentService`, `ApplicationService`, `GroupService` calls through `AssignmentCenterController`.
- **Service optionality**: Guard all service calls; disable affordances if services unavailable.
- **Diff semantics**: When cloning assignments between apps, strip assignment IDs so diff computes correct create/update/delete sets.
- **Cache awareness**: Reuse cached assignments in preview; fall back to on-demand fetch on cache miss.
- **Preview efficiency**: Keep dry-run fast by batching diff computation; show incremental results as they complete.
- **Audit trail**: Append user-visible history entry for every preview/apply/export; enable observability across sessions.

## Key Patterns

### Diff Workflow
1. **Select apps & target groups**: User picks source apps, destination groups, optional filter
2. **Compute diff**: `AssignmentService.diff()` compares existing → proposed assignments
3. **Preview**: Display creates/updates/deletes with conflict warnings (missing group, invalid filter, permission issues)
4. **Apply**: User confirms; `AssignmentService.apply()` executes against Graph API
5. **History**: Record outcome (success/partial/failure) in audit trail

### Batch Operations
- Support copy assignments from one app to many (bulk source)
- Support assign one app to many groups (bulk target)
- Dry-run across all combinations before execution

### Conflict Resolution
- **Missing groups**: Warn and skip
- **Filter validation**: Check filter exists and is applicable
- **Permission gaps**: Surface if user lacks Graph scopes
- **Rollback**: Offer undo for last apply (restore via AssignmentService)

## Guidelines
- **Responsiveness**: Keep workspace interactive during diff computation; show progress.
- **Clarity**: Display diffs in table (app, group, target, intent, action); highlight changes in color.
- **Accessibility**: Keyboard navigation (Tab through sections), clear labels, export diffs to CSV.
- **Error handling**: Validation errors (no apps/groups selected) prevent advance with guidance; API errors surface in banner with retry.
- **Testing**: Unit test diff logic; integration test apply workflows with mocked service.

## Related Modules
- See `@intune_manager/services` for `AssignmentService`, `ApplicationService`, `GroupService`
- See `@intune_manager/ui/applications` for bulk assignment dialog integration
- See `@intune_manager/ui/components` for shared diff/preview widgets
