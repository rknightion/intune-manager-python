# UI Components Agent Guide

## Purpose
- Provide reusable PySide6 widgets (`BusyOverlay`, `ToastManager`, `PageScaffold`, etc.) for consistent cross-module styling.
- Centralize theme/palette management, global dialogs, and async bridging for feature modules.
- Keep components composable, logic-free, and testable with minimal dependencies.

## Module Structure
- **`theme.py`**: `AppPalette`, color schemes, typography constants
- **`layouts.py`**: `PageScaffold`, grid layouts, responsive containers
- **`overlays.py`**: `BusyOverlay` (spinner), progress indicators
- **`notifications.py`**: `ToastManager`, notification queues, auto-dismiss
- **`dialogs.py`**: Reusable dialog templates (confirm, input, error, progress)
- **`badges.py`**: Status badges, labels, tags
- **`alerts.py`**: Alert banners (info, warning, error, success)
- **`context.py`**: `UIContext` (global state: theme, busy, notifications)
- **`commands.py`**: Keyboard shortcut registry, command palette
- **`assignment_bridge.py`**: Bridge for cross-module assignment workflows

## Conventions
- **No business logic**: Widgets remain pure presentation; emit signals for host windows to orchestrate.
- **Styling**: In-code palettes + scoped stylesheets; avoid `.qss` files until theme maturity.
- **Service independence**: Never import services; gracefully handle missing dependencies.
- **Composability**: Design widgets to nest and combine without tight coupling.
- **Async-safe**: Support async operations via signals; never block Qt event loop.

## Key Components

### UIContext (Global State)
Singleton holding:
- Current theme (light/dark)
- Busy overlay state
- Notification queue
- Command registry

### PageScaffold
Composite layout:
- Header (breadcrumb, search bar, action buttons)
- Main content area (scrollable)
- Optional side drawer
- Footer (status bar, pagination)

### Async Pattern
```python
# Emit signal from service/controller
self.operation_completed.emit(result)

# Widget slot updates UI
def on_operation_completed(self, result):
    UIContext.hide_busy()
    UIContext.show_notification("Success")
    self._update_content(result)
```

## Guidelines
- **Composition over inheritance**: Prefer embedding widgets over subclassing.
- **Signal clarity**: Document all signals in docstring (parameters, conditions for emission).
- **Accessibility**: Include `objectName` for testing; support keyboard navigation.
- **Responsiveness**: Avoid `O(n)` layouts; use lazy rendering for large datasets.
- **Testing**: Unit test widget rendering; mock signals for integration tests.

## Related Modules
- See `@intune_manager/ui` for module-level widget patterns
- See `@intune_manager/config` for theme configuration
