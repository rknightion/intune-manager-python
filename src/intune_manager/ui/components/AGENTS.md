# UI Components Agent Guide

## Purpose
- Provide reusable PySide6 widgets (`BusyOverlay`, `ToastManager`, `PageScaffold`, etc.) that deliver consistent styling across modules.
- Centralize theme/palette management and global dialog helpers for use by feature screens.

## Conventions
- Keep widgets composable and avoid business logic; emit Qt signals for host windows to react.
- Style through in-code palettes + scoped stylesheets; avoid external `.qss` until theme tooling (P6.10).
- Ensure each widget gracefully handles missing services (default to no-op).

## Next Steps
- Wire `ToastManager` + `BusyOverlay` into `MainWindow`.
- Extend with command palette + permission banner once Phase 6 flows demand them.
- Add pytest-qt coverage for toast dismissal + overlay focus blocking in Phase 8.

