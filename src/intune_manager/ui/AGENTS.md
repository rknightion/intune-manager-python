# intune_manager.ui – AGENT Brief

## Purpose
- Build the PySide6 interface: windows, dialogs, widgets, and theming for cross-platform Intune management.
- Wire UI events to services via signals/slots and asyncio bridges (`AsyncBridge`).
- Provide consistent, responsive UX across macOS, Windows, and Linux.

## Architecture

### Module Structure
- **`main/`**: `MainWindow` with navigation tabs, global service wiring, shared UI state
- **`applications/`**: App browser, detail view, assignment editor (includes bulk assignment dialog)
- **`devices/`**: Device explorer with tabbed detail drawer (Overview, Hardware, Network, Security, Apps)
- **`groups/`**: Group membership explorer, member add/remove flows, group creation
- **`assignments/`**: Bulk assignment workspace (compare, dry-run, apply, export, history)
- **`dashboard/`**: Tenant health overview, quick actions, cache status
- **`settings/`**: Tenant/app config, MSAL sign-in, permission diagnostics, secret storage
- **`components/`**: Reusable widgets (`BusyOverlay`, `ToastManager`, `PageScaffold`, dialogs, badges)
- **`i18n/`**: Translation manager and catalog bootstrap (`TranslationManager`, `.ts/.qm` assets)

## Conventions
- **Separation of concerns**: UI widgets stay declarative; delegate logic to controllers and services.
- **Async safety**: Use `AsyncBridge.run_async(coro)` for long-running operations; never block the Qt event loop.
- **State management**: Populate UI from `ServiceRegistry` (via dependency injection); emit signals for user actions.
- **Caching**: Reuse cached data (detail drawers, list models) when possible; reflect stale states via `UIContext`.
- **Service optionality**: Guard all service calls with graceful degradation when services are unavailable.

## Key Patterns

### Controller Pattern
Each feature module (applications, devices, groups) has a `Controller` class that:
- Maintains connection to service layer (`ServiceRegistry`)
- Exposes domain methods for widget consumption
- Emits Qt signals for async operation completion
- Handles service-not-available scenarios

### Model Pattern
PySide6 list/tree models extend `QAbstractTableModel` or `QAbstractItemModel`:
- Keep models focused on data projection (sorting, filtering)
- Avoid business logic in views
- Use `set_data_lazy()` for large datasets (≥1k rows) to prevent UI stalls

### Async Pattern
For Graph API calls or database operations:
1. Create coroutine in controller method
2. Emit signal with result or error
3. Widget slot connects to signal and updates UI
4. Use `UIContext` helpers (`set_busy()`, `show_notification()`) for user feedback

## Guidelines
- **Heavy logic in services**: Controllers orchestrate, services implement.
- **Styling**: In-code palettes + scoped stylesheets; avoid external `.qss` until theme tooling maturity.
- **Accessibility**: Keyboard shortcuts (e.g., Ctrl+R for refresh), clear labels, screen reader hints.
- **Responsive**: Use pagination, lazy loading, and incremental rendering for large datasets.
- **Error handling**: Surface errors via notifications/banners; log details via `intune_manager.utils.get_logger()`.
- **Cross-platform**: Test layouts on macOS (Retina), Windows (scaling), and Linux (DPI).

## Cross-Module Dependencies
- **ServiceRegistry**: Central injection point for all service dependencies
- **UIContext**: Global state (busy overlay, toasts, notifications, theme)
- **AsyncBridge**: Qt event loop ↔ asyncio integration
- **Signals**: Prefer `pyqtSignal` over direct callbacks for decoupling

## Related Modules
- See `@intune_manager/services` for business logic backing all UI interactions
- See `@intune_manager/data` for domain models and cache management
- See `@intune_manager/config` for app settings and theme configuration
