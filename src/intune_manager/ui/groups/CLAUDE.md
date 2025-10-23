# Groups Module Agent Guide

## Purpose
- Explore Azure AD / Entra ID groups with search, filtering, and tree/table navigation modes.
- Visualize group membership (paginated, incremental fetch) and enable add/remove flows.
- Support group authoring (create/update/delete) with real-time validation and confirmation flows.
- Expose group selections to assignment editors and other cross-module workflows.

## Module Structure
- **`controller.py`**: `GroupController` — service orchestration, membership fetching, group mutations
- **`models.py`**: `GroupTableModel`, `QStandardItemModel` for tree view, group hierarchy representation
- **`widgets.py`**: `GroupExplorerWidget`, membership detail drawer, add/remove dialogs, create group dialog

## Conventions
- **Service routing**: Route all `GroupService` calls through `GroupController`; widgets stay declarative.
- **Membership fetching**: Use `GroupService.member_stream()` for paginated, incremental loading.
- **Dual views**: Support both table (flat list) and tree (hierarchy) navigation; keep selection in sync.
- **Dialogs for mutations**: Use dedicated dialogs for member add/remove and group creation; keep main surface focused.
- **Confirmation prompts**: Guard deletes/updates behind confirmation; surface results via `UIContext`.
- **Cache management**: Controller caches membership results; refresh on user action or stale signal.
- **Cross-module integration**: Expose `selected_groups()` helper for assignment editors to consume.

## Key Patterns

### Membership Incremental Loading
- `GroupService.member_stream()` yields page-sized batches
- Controller batches updates (every 50 members) to prevent UI thrashing
- User can interact while loading (search, scroll)
- "Load more" button for manual pagination

### Add/Remove Workflows
1. Member add dialog: Search users, select, confirm
2. Graph API creates assignment via `GroupService.add_member()`
3. UI updates membership list optimistically; reconcile on service callback
4. Errors surface in inline notification

### Tree Hierarchy
- Group nesting (security groups containing groups)
- Lazy-expand on user interaction
- Collapse/expand state persisted in controller

## Guidelines
- **Performance**: Paginate membership; lazy-load hierarchy nodes.
- **Accessibility**: Keyboard navigation (arrow keys for tree, Tab for focus), clear labels.
- **Error handling**: Validation errors (duplicate member, invalid user) show in dialog; API errors in notification bar.
- **Testing**: Unit test controller membership fetching; integration test dialogs with mocked service.

## Related Modules
- See `@intune_manager/services` for `GroupService` implementation
- See `@intune_manager/ui/assignments` for group selection integration
- See `@intune_manager/data/models` for `DirectoryGroup` domain model
