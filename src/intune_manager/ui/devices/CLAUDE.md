# Devices Module Agent Guide

## Purpose
- Provide a responsive managed device explorer with search, sorting, filtering, and metadata export.
- Surface comprehensive device detail (Overview, Hardware, Network, Security, Installed Apps tabs) with incremental caching.
- Orchestrate device sync, refresh, and action flows (e.g., remote actions) via `DeviceController`.
- Optimize for large datasets (1k+ devices) with lazy loading, pagination, and incremental renders.

## Module Structure
- **`controller.py`**: `DeviceController` — service orchestration, cache management, async signal emission
- **`models.py`**: `DeviceTableModel` (extends `QAbstractTableModel`), lazy-load support, sort/filter proxy
- **`widgets.py`**: `DeviceExplorerWidget`, detail drawer (tabbed), search/filter bar, action buttons

## Conventions
- **Service routing**: Route all `DeviceService` calls through `DeviceController`; widgets stay declarative.
- **Lazy loading**: For datasets ≥1k rows, use `DeviceTableModel.set_devices_lazy()` (batch size 400 rows).
- **Detail drawer**: Populate tabs incrementally; cache detail objects to avoid re-fetching on drawer re-open.
- **Async safety**: All Graph/DB calls via `AsyncBridge`; never block the Qt event loop.
- **User feedback**: Use `UIContext` helpers (`set_busy()`, `show_notification()`, `show_banner()`) for consistency.
- **Search/sort**: Delegate to `QSortFilterProxyModel`; keep models focused on projection.
- **Service optionality**: Guard remote actions behind `ServiceRegistry` checks; disable UI affordances if unavailable.

## Key Patterns

### Lazy Loading
For 1k+ device rows:
1. `set_devices_lazy(devices)` queues batch updates (~400 rows/tick)
2. UI remains responsive; user can search/sort while loading
3. Subsequent scrolls fetch from already-loaded data
4. Detail drawer populates async on expand

### Detail Drawer Cache
- `DeviceDetailCache` holds expanded device contexts
- On drawer open, check cache before fetching from Graph
- Refresh button forces Graph fetch + cache update
- Cache expires when main device list refreshes

### Filtering & Search
- `QSortFilterProxyModel` filters on device name, user email, compliance state
- Fuzzy matching on device lookup for quick navigation
- Export selected devices to CSV/JSON

## Guidelines
- **Performance**: Avoid `O(n)` operations during list rendering; use lazy loading for large datasets.
- **Caching**: Reuse detail cache between drawer interactions; clear on main list refresh.
- **Accessibility**: Keyboard shortcuts (Ctrl+F for search, Ctrl+R for refresh), clear labels.
- **Error handling**: Network errors surface in notification bar; validation errors (e.g., empty filter) show inline.
- **Testing**: Unit test models; integration test lazy loading with mocked service.

## Related Modules
- See `@intune_manager/services` for `DeviceService` implementation
- See `@intune_manager/ui/components` for shared widgets (overlays, dialogs)
- See `@intune_manager/data/models` for `ManagedDevice` domain model
