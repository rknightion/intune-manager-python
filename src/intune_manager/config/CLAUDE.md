# intune_manager.config – AGENT Brief

## Purpose
- Centralize environment configuration (dotenv loading, typed settings dataclass).
- Provide platform-specific config/cache paths (macOS/Windows/Linux via `platformdirs`).
- Define application constants (Graph scopes, cache TTLs, log levels, feature flags).

## Module Structure
- **`settings.py`**: `SettingsManager` (dotenv + env var loader), `Settings` dataclass (tenant ID, client ID, etc.)
- **`paths.py`**: Platform-specific directories (config, cache, logs) via `platformdirs`
- **`logging.py`**: Logging setup (structlog + loguru pipeline, rotating file handler)
- **`constants.py`**: App-wide constants (Graph scopes, cache TTLs, pagination batch sizes, etc.)

## Conventions
- **Dotenv first**: Load `.env` + `.env.local` (for secrets) from project root; env vars override.
- **Type safety**: Use `SettingsManager.load() → Settings` dataclass; never raw dict/string lookups.
- **Platform abstraction**: Hide OS-specific paths behind helper functions; code never hardcodes `/home/` or `~/`.
- **Secrets isolation**: Never store secrets in config file; use env vars + keyring storage.
- **Feature flags**: Define in `Settings`; enable per-tenant or per-session as needed.
- **Logging config**: Centralize structlog + loguru setup; export `get_logger()` factory for modules.

## Key Patterns

### Settings Loading
```python
settings = SettingsManager.load()
print(settings.tenant_id)       # From env or .env
print(settings.graph_scopes)    # Default or overridden
print(settings.cache_ttl_devices)  # Constant
```

### Path Management
```python
config_dir = get_config_dir()  # ~/.config/IntuneManager on Linux, etc.
cache_dir = get_cache_dir()    # ~/.cache/IntuneManager
log_file = get_log_file()      # cache_dir/logs/app.log
```

### Logging
```python
logger = get_logger("intune_manager.services")
logger.info("action", device_id=uuid, status="synced")  # Structured
```

## Guidelines
- **Validation**: Check required settings (tenant ID, client ID) on app startup; fail early.
- **Defaults**: Document all default values in code comments; provide examples in `.env.example`.
- **Secrets**: NEVER commit `.env` (only `.env.example`); add to `.gitignore`.
- **Cache strategy**: Define TTLs per domain (devices 15m, apps 20m, etc.); adjustable via settings.
- **Testing**: Use `SettingsManager` with test-specific .env file; avoid side effects on user config.
- **Migrations**: When adding new config keys, update `migration.txt` with upgrade instructions.

## Related Modules
- See `@intune_manager/auth` for secret storage patterns
- See `@intune_manager/utils` for logger factory usage
- See root AGENTS.md for app-wide constants reference
