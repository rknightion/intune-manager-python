# intune_manager.data.storage – AGENT Brief

## Scope
- Handle binary attachments (icons, exported reports, log bundles) with disk quota enforcement.
- Provide convenience APIs for storing and retrieving cached files referenced by repositories/UI.

## Expectations
- Keep storage isolated in the cache directory (per-tenant subfolders when relevant).
- Track total usage and expire LRU entries when exceeding quota.
- Expose async-friendly helpers where long-running disk ops are expected; surface metadata via lightweight pydantic models.
