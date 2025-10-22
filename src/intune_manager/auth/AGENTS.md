# intune_manager.auth – AGENT Brief

## Purpose
- Manage all authentication and token lifecycle logic (MSAL integrations, account storage, permission checks).
- Expose async-friendly managers/signals for UI and services to observe login state.

## Guidelines
- Keep platform-specific secure storage adapters behind dedicated modules (e.g., keyring wrappers).
- Prefer dependency-injected Graph clients; do not import UI layers.
- Record auth flow decisions and new scopes in `migration.txt` progress notes.
