# intune_manager.services – AGENT Brief

## Purpose
- Implement business logic for Microsoft Graph operations and cache orchestration.
- Provide async facades over repositories + Graph clients, transparent to UI layer.
- Coordinate cross-service workflows (e.g., bulk assignments involving devices, apps, groups, filters).

## Module Structure
Each domain (devices, applications, groups, assignments, filters, etc.) gets a dedicated service module:
- `DeviceService`: Device sync, detail fetching, compliance reporting
- `ApplicationService`: App catalog, metadata, icon caching, assignment tracking
- `GroupService`: Group membership, add/remove flows, group creation/update
- `AssignmentService`: Assignment diff/apply, bulk operations, history tracking
- `AssignmentFilterService`: Filter list, filter-based targeting
- `AuditService`: Audit log fetch, filtering, export

## Conventions
- **No UI imports**: Services remain platform-agnostic; UI consumes via `ServiceRegistry`.
- **Graph routing**: All Microsoft Graph calls go through `intune_manager.graph` (rate limiting, retry, logging).
- **Repository abstraction**: Services call `data.repositories` methods; never raw SQL or ORM details.
- **Async-first**: All I/O is async; return coroutines that UI orchestrates via `AsyncBridge`.
- **Error propagation**: Raise categorized exceptions (`GraphAPIError`, `AuthenticationError`, `PermissionError`) for UI handling.
- **Caching strategy**: Leverage repository cache TTLs; services rarely override (except forced refresh on user action).

## Key Patterns

### Service Methods
- **Fetch**: `async def list_*() -> list[Model]` — fetch from repository (uses cache if fresh)
- **Refresh**: `async def refresh_*() -> list[Model]` — force Graph API fetch, update cache
- **Mutate**: `async def create/update/delete_*(...) -> Model` — apply to Graph, update cache, return result
- **Query**: `async def get_*_by_*(filter) -> Model | None` — repository lookup (cache-backed)

### Cross-Service Coordination
Example: bulk assignment workflow
1. `AssignmentService.diff()` compares requested vs. existing assignments
2. Uses `ApplicationService.list_applications()` and `GroupService.list_groups()` for context
3. Uses `AssignmentFilterService.get_filter()` if filter targeting is involved
4. Returns structured diff (creates, updates, deletes) for UI preview
5. `AssignmentService.apply()` executes diff against Graph API and cache

## Guidelines
- **Isolation**: Services should not call each other; UI orchestrates multi-service flows via controllers.
- **Testability**: Write unit tests with mocked repositories and Graph clients; avoid hitting live API in tests.
- **Logging**: Use `intune_manager.utils.get_logger()` for all service operations; log request/response sketches.
- **Permissions**: Check auth state early; fail fast if required scopes missing (use `auth.PermissionChecker`).
- **Cache awareness**: Document cache TTLs and when auto-refresh is triggered (e.g., on every app list, or only on user action).
- **Breaking changes**: When modifying service signatures, update `migration.txt` with migration notes.

## Related Modules
- See `@intune_manager/graph` for Graph API client patterns and utilities
- See `@intune_manager/data/repositories` for cache-aware data access
- See `@intune_manager/auth` for permission checking and token management
- See `@intune_manager/ui` (controllers) for service orchestration patterns
