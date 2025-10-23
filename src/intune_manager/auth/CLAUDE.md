# intune_manager.auth – AGENT Brief

## Purpose
- Manage authentication lifecycle (MSAL token acquisition, caching, refresh) and secret storage.
- Provide permission checking (scopes vs. requirements) and account management.
- Expose async-friendly APIs for UI and services to acquire tokens and verify auth state.

## Module Structure
- **`auth_manager.py`**: `AuthManager` — MSAL wrapping, token lifecycle, async token helpers
- **`secret_store.py`**: `SecretStore` — keyring/OS credential store for secrets (client secret, etc.)
- **`permission_checker.py`**: `PermissionChecker` — JWT scope extraction and validation

## Conventions
- **Async-first**: All token operations are async (`acquire_token_async()`, etc.); never block UI thread.
- **Error categorization**: Raise `AuthenticationError`, `PermissionError` (vs generic exceptions) for UI handling.
- **Token caching**: MSAL handles in-memory + persistent cache (to `~/.cache/IntuneManager/token_cache.bin`).
- **Secret storage**: Never persist secrets in code/config files; use `SecretStore` for keyring access.
- **Scope management**: Document all required Graph scopes; check via `PermissionChecker` early in workflows.
- **No UI imports**: Remain UI-agnostic; UI imports auth, not vice-versa.

## Key Patterns

### Token Acquisition
```python
# Interactive sign-in
token = await auth_manager.sign_in_interactive(scopes=["user.read"])

# Silent refresh
token = await auth_manager.acquire_token_async(scopes=["user.read"])

# Sign out
await auth_manager.sign_out()
```

### Permission Checking
```python
checker = PermissionChecker(token)
missing_scopes = checker.missing_scopes(required=["DeviceManagementManagedDevices.Read.All"])
if missing_scopes:
    # Prompt user to re-sign-in with new scopes
```

### Secret Storage
```python
# Save client secret
secret_store.save_secret("client_secret", value)

# Retrieve (may prompt for OS password on some platforms)
secret = secret_store.get_secret("client_secret")

# Delete
secret_store.delete_secret("client_secret")
```

## Guidelines
- **Scope documentation**: Comment all required scopes per feature; update `migration.txt` when scopes change.
- **Token lifecycle**: Never cache tokens in-memory beyond request (MSAL handles persistence).
- **Error messages**: Provide actionable guidance (e.g., "Sign in required" vs. "Missing permissions").
- **Logging**: Log auth events (sign-in, token refresh, scope checks); never log token values.
- **Testing**: Mock MSAL + `SecretStore` in unit tests; avoid live auth in CI.
- **Multi-tenant**: Support current user context switching (e.g., different tenant IDs per session).

## Related Modules
- See `@intune_manager/config` for settings (tenant ID, client ID, redirect URI)
- See `@intune_manager/ui/settings` for auth flow UI
- See `@intune_manager/services` for service-level auth checks
