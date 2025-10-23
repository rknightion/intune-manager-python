# intune_manager.graph – AGENT Brief

## Purpose
- Wrap `msgraph-beta-sdk-python` client with rate limiting, retry logic, and structured error handling.
- Provide pagination helpers, batch operation utilities, and endpoint shortcuts for common Intune queries.
- Centralize authentication injection and logging to keep services clean.

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
- **Beta API**: Default to beta endpoint (`https://graph.microsoft.com/beta`); configurable per request.
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
- **Testing**: Unit test rate limiter + error mapping; mock SDK for service integration tests.
- **Version compatibility**: Document minimum SDK version; validate on startup.

## Related Modules
- See `@intune_manager/auth` for token/authentication injection
- See `@intune_manager/services` for service-layer Graph usage
- See `@intune_manager/data/repositories` for cache management over Graph calls
