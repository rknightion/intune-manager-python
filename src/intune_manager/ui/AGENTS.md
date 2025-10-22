# intune_manager.ui – AGENT Brief

## Purpose
- Build the PySide6 interface: windows, dialogs, widgets, and theming.
- Wire UI events to services via signals/slots or asyncio bridges.

## Guidelines
- Keep heavy logic in services/data; UI components should orchestrate and present.
- Maintain accessibility (keyboard shortcuts, screen reader text) and cross-platform styling.
- Log new UX patterns or reusable widgets in `migration.txt` when they affect other modules.
