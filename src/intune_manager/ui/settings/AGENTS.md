# intune_manager.ui.settings – AGENT Guide

## Purpose
- Provide configuration experiences for tenant/app registration, MSAL authentication, and permission diagnostics.
- Surface secure secret handling (keyring/OS credential store) with user-friendly workflows.
- Surface cache health, diagnostics, and telemetry preferences alongside core settings.
- Communicate configuration changes and auth state updates to the main application.

## Module Structure
- **`controller.py`**: `SettingsController` — config management, auth flows, secret storage orchestration
- **`widgets.py`**: Settings form, tenant/client config fields, secret input with visibility toggle
- **`page.py`**: Tabbed settings shell with cache diagnostics, log export, telemetry toggle, and about panel
- **`dialog.py`**: MSAL sign-in dialog, permission diagnostic dialog

## Conventions
- **Separation of concerns**: Controllers handle config/auth logic; widgets focus on presentation.
- **Async operations**: All long-running ops (sign-in, secret save) emit signals; UI shows progress.
- **Secret handling**: Never store secrets in memory longer than needed; use `SecretStore` for persistence.
- **No file access**: Always go through `SettingsManager` and `SecretStore` (never touch config files directly).
- **Signal communication**: Emit signals for successful auth, config updates, permission changes.
- **Logging**: Log all config changes, auth events, and diagnostic findings via `intune_manager.utils.get_logger()`.

## Key Workflows

### Initial Configuration
1. User enters tenant ID, client ID, redirect URI
2. `SettingsController` validates against Graph API (MS Entra permissions)
3. On success, saves to config file
4. Emit `config_updated` signal to main window

### MSAL Sign-In
1. User clicks "Sign In" → `SettingsController.sign_in_interactive()`
2. Dialog launches MSAL flow (handles token acquisition + caching)
3. On success, emit `auth_completed` signal with user info
4. Main window updates UI (show username, enable features)

### Permission Diagnostics
1. Fetch current token's granted scopes via `PermissionChecker`
2. Compare against required scopes for each feature
3. Surface missing scopes with "Request" buttons
4. User can trigger new sign-in to grant missing permissions

### Secret Storage
1. User enters client secret
2. `SettingsController` calls `SecretStore.save_secret()`
3. Secret persists to keyring/OS credential store (not file)
4. On load, retrieve via `SecretStore.get_secret()` (may prompt for OS password)

## Guidelines
- **Validation**: Validate tenant/client IDs early (format + MS Entra availability).
- **Error clarity**: Auth failures show specific reasons (invalid credentials, wrong tenant, missing scopes).
- **Recovery**: Provide "Reconfigure" and "Sign In Again" buttons for common errors.
- **Security**: Never log secrets; mask in diagnostics output.
- **Accessibility**: Keyboard shortcuts (Tab for field navigation, Ctrl+S for save), screen reader labels.
- **Testing**: Unit test controller with mocked `SettingsManager` and `SecretStore`; integration test dialogs with real auth (or mocked MSAL).

## Related Modules
- See `@intune_manager/config` for `SettingsManager` implementation
- See `@intune_manager/auth` for `AuthManager`, `SecretStore`, `PermissionChecker`
- See `@intune_manager/ui` for signal/slot patterns
