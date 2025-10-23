# intune_manager.graph – AGENT Brief

## Purpose
- Provide direct Microsoft Graph REST API client using httpx with MSAL authentication, rate limiting, retry logic, and structured error handling.
- Provide pagination helpers, batch operation utilities, and endpoint shortcuts for common Intune queries.
- Centralize authentication injection and logging to keep services clean.

## Architecture Decision: Why Not Use msgraph-beta-sdk?

This module implements a custom httpx-based Graph client instead of using Microsoft's official SDK. Rationale:

1. **Version Flexibility**: Mix v1.0 GA (stable) and beta endpoints per-path via override system
2. **Rate Limiting**: Custom 20-second window tracking with exponential backoff for bulk operations
3. **Batch Operations**: Manual batch payload construction with version-aware request merging
4. **Telemetry**: Rich timing, retry counts, and error categorization for diagnostics
5. **Control**: Direct access to HTTP layer for advanced debugging and testing
6. **Simplicity**: Avoid heavy SDK dependency tree (~15 packages) when we only need HTTP + auth

We use MSAL directly for token acquisition/refresh, then inject Bearer tokens into httpx requests.

## Module Structure
- **`client.py`**: `RateLimitedAsyncClient`, Graph request builder wrappers, pagination helpers
- **`rate_limiter.py`**: `RateLimiter` — 20-second window tracking, exponential backoff, batch splitting
- **`errors.py`**: Categorized exceptions (`GraphAPIError`, `AuthenticationError`, `PermissionError`, `RateLimitError`)
- **`endpoints.py`**: Pre-built endpoint paths (e.g., `/deviceManagement/managedDevices`)

## Conventions
- **Rate limiting**: All requests go through `RateLimiter`; limits: 100 writes/window, 1000 total/window.
- **Retry logic**: Exponential backoff with jitter (1s → 32s); configurable per endpoint.
- **Error mapping**: Graph response codes → categorized exceptions for UI handling.
- **Async-first**: All operations are async; never block on network I/O.
- **Pagination**: `iter_collection()` auto-handles `@odata.nextLink`; transparent to consumers.
- **Version switching**: Default to v1.0 GA; override per-path for beta-only features via `version_overrides`.
- **Logging**: Structured logs with request/response sketches (no sensitive data); integrate with `config.logging`.

## Key Patterns

### Client Factory
```python
client = RateLimitedAsyncClient(
    auth_provider,
    rate_limiter=RateLimiter(),
    logger=get_logger("graph")
)
```

### Pagination
```python
async for device_page in client.iter_collection(
    "/deviceManagement/managedDevices",
    item_type=ManagedDevice
):
    # Process page-sized batches
    process_devices(device_page)
```

### Error Handling
```python
try:
    response = await client.request_json("/...")
except PermissionError as e:
    # Missing scopes; prompt user
except RateLimitError as e:
    # Backoff and retry
```

## Guidelines
- **Scope documentation**: Comment required scopes per endpoint; update `migration.txt` on scope changes.
- **Batch operations**: For bulk mutations, use Graph batch API (`/batch`); split if ≥20 requests.
- **Caching**: Do not cache at this layer (services handle cache TTLs).
- **Logging**: Log request attempts + outcomes; never log auth headers or response payloads (only sketches).
- **Testing**: Unit test rate limiter + error mapping; mock httpx responses for service integration tests.
- **Version management**: Use `version_overrides` to specify beta-only endpoints; default to v1.0 GA for stability.

## Related Modules
- See `@intune_manager/auth` for token/authentication injection
- See `@intune_manager/services` for service-layer Graph usage
- See `@intune_manager/data/repositories` for cache management over Graph calls
