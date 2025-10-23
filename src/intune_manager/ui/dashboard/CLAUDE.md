# Dashboard Module Agent Guide

## Purpose
- Provide an at-a-glance overview of tenant health (device/app counts, cache freshness, auth status).
- Expose quick actions (refresh all, export, diagnostics) and surface configuration warnings.
- Trigger global state updates and alert users to stale caches or permission issues.

## Module Structure
- **`controller.py`**: `DashboardController` — service aggregation, refresh orchestration, stat updates
- **`widgets.py`**: Card-based layout (device count, app count, cache status, auth state), action buttons

## Conventions
- **Async fetching**: All data fetches via `AsyncBridge`; never block the Qt event loop.
- **Lightweight**: Dashboard is summary-only; detailed exploration happens in dedicated modules.
- **Service optionality**: Degrade gracefully when services unavailable; show "N/A" instead of errors.
- **Cache awareness**: Display cache freshness (e.g., "Devices refreshed 3 mins ago"); trigger refresh via button.
- **Quick actions**: Include global refresh, export, settings, diagnostics buttons.

## Key Patterns

### Health Metrics
- **Device count**: Total managed devices (from cache)
- **App count**: Total managed apps (from cache)
- **Cache freshness**: Time since last successful sync per domain
- **Auth status**: Current user, tenant, token expiry countdown
- **Warnings**: Missing configuration (tenant ID, client secret), permission gaps

### Refresh Orchestration
1. User clicks "Refresh All"
2. Dashboard calls `DashboardController.refresh_all()`
3. Controller triggers refresh on all service repositories in parallel
4. UI shows progress (e.g., "Syncing devices...")
5. As each domain completes, update corresponding card
6. Finally update cache timestamp cards

### Configuration Warnings
- Missing tenant ID/client ID → "Configure Settings" link
- Missing Graph scopes → "Fix Permissions" link
- Failed auth → "Sign In" link

## Guidelines
- **Performance**: Pre-compute counts from cache; avoid expensive Graph calls on dashboard load.
- **Clarity**: Use icons + color coding (green: healthy, yellow: stale, red: error) for quick scanning.
- **Accessibility**: Keyboard shortcuts for quick actions (e.g., Ctrl+Shift+R for refresh).
- **Error handling**: Surface errors in cards without blocking other cards (e.g., device count fails, but app count succeeds).
- **Testing**: Unit test metric aggregation; integration test refresh orchestration with mocked services.

## Related Modules
- See `@intune_manager/services` for service health/status endpoints
- See `@intune_manager/ui/settings` for configuration shortcuts
- See `@intune_manager/ui/components` for card and badge styling
