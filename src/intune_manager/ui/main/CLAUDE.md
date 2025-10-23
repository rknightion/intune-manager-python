# intune_manager.ui.main – AGENT Guide

## Purpose
- Provide the PySide6 application shell (`MainWindow`) with tab-based navigation orchestration.
- Manage high-level UI state (current tab, service availability, global signals).
- Coordinate cross-module communication via `ServiceRegistry` and `UIContext`.
- Ensure all child widgets are ready for async updates and never block the Qt event loop.

## Module Structure
- **`main.py`** (or `__main__.py`): Application entry point, `MainWindow` initialization, service wiring
- **`MainWindow`**: Tab widget for (Dashboard, Devices, Applications, Groups, Assignments, Settings)
- **`ServiceRegistry`**: Dependency injection container for all services (lazily instantiated)
- **`UIContext`**: Global singleton (theme, busy state, notification queue)

## Conventions
- **Service wiring**: Create all services via `ServiceRegistry` on app startup; inject into widgets.
- **Widget composition**: Each tab delegates to a feature module (e.g., `DeviceExplorerWidget` in devices module).
- **No business logic**: Keep `MainWindow` focused on navigation, window state, and signal routing.
- **Cross-module signals**: Emit signals when global state changes (auth, config, theme); child widgets listen.
- **Graceful degradation**: If a service fails to init, disable that tab's affordances and show guidance.

## Key Responsibilities

### Window Management
- Window sizing, positioning, geometry persistence (across sessions)
- Maximize/restore state
- Platform-specific behaviors (macOS menu bar, Windows taskbar)

### Navigation
- Tab widget with feature panes (Dashboard, Devices, Applications, Groups, Assignments, Settings)
- Keyboard shortcuts for tab switching (Ctrl+1, Ctrl+2, etc.)
- Breadcrumb/navigation state tracking

### Service Registry
```python
class ServiceRegistry:
    @staticmethod
    def get_device_service() -> DeviceService:
        # Lazy init, singleton

    @staticmethod
    def get_application_service() -> ApplicationService:
        # Lazy init, singleton
```

### Global State Management
- Auth state changes (login/logout)
- Config changes (tenant, permissions)
- Theme changes (light/dark)
- All child widgets listen via `UIContext` signals

### Error Handling
- Service init failures logged + user notified (bottom banner)
- Tab disable + "Configure" button for permission errors
- Retry mechanisms for transient failures

## Guidelines
- **Keep it lean**: Only ~50-100 LOC for `MainWindow` after dependencies injected.
- **Signal discipline**: Define clear signals for major state changes; avoid spaghetti signal connections.
- **Testing**: Unit test service wiring; integration test tab navigation with pytest-qt.
- **Performance**: Lazy-load tab content (only populate on first click); cache populated tabs.
- **Accessibility**: Global keyboard shortcuts, window title reflects current state, screen reader support.

## Related Modules
- See `@intune_manager/ui` for overall UI architecture
- See `@intune_manager/ui/components` for `UIContext` and shared widgets
- See `@intune_manager/config` for app settings (window geometry, theme)
