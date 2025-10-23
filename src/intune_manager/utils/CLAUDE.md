# intune_manager.utils – AGENT Brief

## Purpose
- Provide shared utilities (async helpers, formatting, telemetry) used across multiple modules.
- Keep cross-cutting concerns (logging, async bridging) centralized to avoid duplication.
- Host patterns that don't fit into domain-specific modules but support the entire app.

## Module Structure
- **`logging.py`**: `get_logger()` factory, structured logging configuration, file path utilities
- **`asyncio.py`**: `AsyncBridge` (Qt ↔ asyncio integration), interval scheduling, delayed callbacks
- **`formatting.py`**: Human-readable sizes (bytes → MB), date formatting, truncation helpers
- **`validation.py`**: Email/UUID/ID validation, common regex patterns
- **`decorators.py`**: `@async_safe`, `@rate_limited`, `@cached` helpers for common patterns

## Conventions
- **Minimal imports**: Utilities must not import services, UI, or domain modules (to avoid circular deps).
- **Focused scope**: Each utility module addresses one cross-cutting concern (logging, async, formatting).
- **No business logic**: Utilities are stateless helpers; state belongs in services/data.
- **Testing**: All utilities are thoroughly unit-tested; no mocking required (pure functions).
- **Documentation**: Clear docstrings with examples; explain when/why to use each helper.

## Key Utilities

### Logging
```python
logger = get_logger("intune_manager.services.devices")
logger.info("device_synced", device_id=uuid, status="compliant")
log_file = get_log_file_path()  # Path to current rotating log
```

### Async Bridging (Qt ↔ asyncio)
```python
bridge = AsyncBridge()

# Run async coroutine from Qt slot
bridge.run_async(fetch_devices())

# Connect to completion signal
bridge.task_completed.connect(self.on_complete)
```

### Formatting
```python
human_size = format_bytes(1024 * 1024)  # "1.0 MB"
date_str = format_date(datetime.now())  # "Oct 23, 2025"
truncated = truncate_text("long text...", max_len=50)
```

## Guidelines
- **Isolation**: Never import from services, data, or ui; only import from other utils or external libs.
- **Purity**: Write pure functions where possible; state belongs in services/data layers.
- **Testability**: All utilities are trivially testable without mocks (unit test coverage ≥95%).
- **Reusability**: Promote to dedicated module if utility grows >100 LOC or becomes complex.
- **Versioning**: Document any changes to utility signatures in `migration.txt`.

## Related Modules
- See `@intune_manager/config` for logging initialization
- See root AGENTS.md for architectural patterns using these utilities
