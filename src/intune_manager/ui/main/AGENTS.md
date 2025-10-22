# intune_manager.ui.main – AGENT Brief

## Purpose
- Provide the PySide6 application shell (`MainWindow`) and navigation scaffolding.
- Manage high-level UI orchestration, wiring service events into widgets and maintaining shared UI state.

## Guidelines
- Keep business logic out of UI classes; delegate to services via `ServiceRegistry`.
- Ensure widgets are ready for async updates via `AsyncBridge` and avoid blocking the Qt event loop.
- All new panes should prefer composition (sub-widgets per module) and remain testable with pytest-qt.
