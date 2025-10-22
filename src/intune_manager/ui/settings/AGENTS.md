# intune_manager.ui.settings – AGENT Brief

## Scope
- Provide configuration experiences for tenant/app registration, MSAL login, and permission diagnostics.
- Surface secure secret handling (keyring) and communicate status updates to the rest of the UI.

## Expectations
- Keep business rules in controllers/view models; widgets should only deal with layout and presentation logic.
- Emit PySide6 signals for long-running actions so other components can react (status overlays, navigation guards).
- Always consult `SettingsManager` / `SecretStore` instead of touching files directly.
- Log noteworthy actions via `intune_manager.utils.get_logger` and bubble user-facing feedback through signals.
