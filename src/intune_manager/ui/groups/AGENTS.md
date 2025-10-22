# Groups Module Agent Guide

## Purpose
- Explore Azure AD / Entra ID groups with quick filters and cached metadata.
- Visualise membership and enable add/remove flows without leaving the app.
- Support group authoring (create/update/delete) while maintaining assignment context.

## Conventions
- Keep service access funnelled through `GroupController`; never reach into `GroupService` directly from views.
- Cache membership results per group to avoid repeated Graph calls; refresh explicitly when requested.
- Use dialogs for member add/remove and group creation to keep the main surface focused on discovery.
- Guard all mutating actions behind confirmation prompts and surface results via `UIContext`.
- Prepare for cross-module interactions (assignment editors) by exposing selected group details through controller helpers.

## Next Steps
- Add dynamic membership query editor in a dedicated dialog.
- Surface nested group hierarchy and owner lists.
- Integrate drag-drop between group list and assignment editors once available.

