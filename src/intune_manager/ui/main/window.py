from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable, Dict

from PySide6.QtCore import Qt, QSize, QSettings, QUrl
from PySide6.QtGui import (
    QCloseEvent,
    QDesktopServices,
    QIcon,
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QSystemTrayIcon,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from intune_manager.config import FirstRunStatus, detect_first_run
from intune_manager.services import (
    ServiceErrorEvent,
    ServiceRegistry,
    SyncProgressEvent,
)
from intune_manager.ui.components import (
    AlertBanner,
    BusyOverlay,
    CommandAction,
    CommandPalette,
    CommandRegistry,
    PageScaffold,
    ShortcutDefinition,
    ShortcutHelpDialog,
    TenantBadge,
    ThemeManager,
    ToastLevel,
    ToastManager,
    UIContext,
)
from intune_manager.ui.assignments import AssignmentsWidget
from intune_manager.ui.applications import ApplicationsWidget
from intune_manager.ui.dashboard import DashboardWidget
from intune_manager.ui.devices import DevicesWidget
from intune_manager.ui.groups import GroupsWidget
from intune_manager.ui.reports import ReportsWidget
from intune_manager.ui.settings import SettingsPage
from intune_manager.utils import get_logger, safe_mode_enabled, safe_mode_reason
from intune_manager.utils.asyncio import AsyncBridge


logger = get_logger(__name__)


@dataclass(slots=True)
class NavigationItem:
    key: str
    label: str
    icon: QIcon | None = None


class MainWindow(QMainWindow):
    """Primary PySide6 window hosting Intune Manager modules."""

    NAV_ITEMS: tuple[NavigationItem, ...] = (
        NavigationItem("dashboard", "Dashboard"),
        NavigationItem("devices", "Devices"),
        NavigationItem("applications", "Applications"),
        NavigationItem("assignments", "App Assignments"),
        NavigationItem("groups", "Groups"),
        NavigationItem("reports", "Reports"),
        NavigationItem("settings", "Settings"),
    )

    def __init__(
        self,
        services: ServiceRegistry,
        *,
        parent: QWidget | None = None,
        startup_crash_info: dict[str, str] | None = None,
    ) -> None:
        super().__init__(parent)
        self._services = services
        self._bridge = AsyncBridge()
        self._stack = QStackedWidget()
        self._nav_list = QListWidget()
        self._pages: Dict[str, QWidget] = {}
        self._content_container: QWidget | None = None
        self._alert_banner: AlertBanner | None = None
        self._settings_store = QSettings("IntuneManager", "IntuneManagerApp")
        self._theme_manager = ThemeManager()
        self._toast_manager: ToastManager | None = None
        self._tray_icon: QSystemTrayIcon | None = None
        self._busy_overlay: BusyOverlay | None = None
        self._command_registry = CommandRegistry()
        self._command_palette: CommandPalette | None = None
        self._ui_context: UIContext | None = None
        self._tenant_badge = TenantBadge()
        self._status_default_message = "Ready"
        self._busy_default_message = "Working…"
        self._subscriptions: list[Callable[[], None]] = []
        self._shortcuts: list[QShortcut] = []
        self._shortcut_definitions: list[ShortcutDefinition] = []
        self._shortcuts_dialog: ShortcutHelpDialog | None = None
        self._sync_in_progress = False
        self._dashboard_widget: DashboardWidget | None = None
        self._settings_page: SettingsPage | None = None
        self._banner_action: Callable[[], None] | None = None
        self._first_run_status: FirstRunStatus | None = None
        self._startup_crash_info = startup_crash_info
        self._crash_report_path: Path | None = None

        self._configure_window()
        self._build_layout()
        self._connect_banner_events()
        self._initialize_components()
        self._populate_navigation()
        self._register_shortcuts()
        self._register_commands()
        self._connect_navigation()
        self._connect_services()
        self._restore_window_preferences()
        self._evaluate_onboarding_state()
        self._display_safe_mode_banner()
        self._display_previous_crash_notice()

    # ------------------------------------------------------------------ Setup

    def _configure_window(self) -> None:
        self.setWindowTitle("Intune Manager")
        self.resize(1440, 900)  # Increased for better dashboard layout
        self.setMinimumSize(QSize(1200, 700))
        status = QStatusBar()
        status.setObjectName("MainStatusBar")
        status.setSizeGripEnabled(False)
        status.showMessage(self._status_default_message)
        status.addPermanentWidget(self._tenant_badge)
        self.setStatusBar(status)

    def _build_layout(self) -> None:
        central = QWidget()
        outer_layout = QVBoxLayout(central)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self._alert_banner = AlertBanner(parent=central)
        self._alert_banner.hide()
        outer_layout.addWidget(self._alert_banner)

        content = QWidget()
        self._content_container = content
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        sidebar_width = 150  # Shrink navigation rail ~150px to free more canvas space
        self._nav_list.setObjectName("NavigationList")
        self._nav_list.setFixedWidth(sidebar_width)
        self._nav_list.setMinimumWidth(sidebar_width)
        self._nav_list.setSpacing(2)
        self._nav_list.setAlternatingRowColors(True)
        self._nav_list.setSelectionMode(QListWidget.SingleSelection)
        self._nav_list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._nav_list.setMouseTracking(True)
        self._nav_list.setWordWrap(True)
        self._nav_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._nav_list.setSizePolicy(
            QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding),
        )

        content_layout.addWidget(self._nav_list)
        content_layout.addWidget(self._stack, stretch=1)

        outer_layout.addWidget(content, stretch=1)
        self.setCentralWidget(central)

    def _connect_banner_events(self) -> None:
        if self._alert_banner is None:
            return
        self._alert_banner.actionTriggered.connect(self._handle_banner_action_triggered)
        self._alert_banner.dismissed.connect(self._handle_banner_dismissed)

    def _initialize_components(self) -> None:
        central = self.centralWidget()
        if central is None:
            return
        self._busy_overlay = BusyOverlay(central)
        self._toast_manager = ToastManager(central, theme=self._theme_manager)
        if QSystemTrayIcon.isSystemTrayAvailable():
            icon = self.windowIcon()
            if icon.isNull():
                icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
            tray = QSystemTrayIcon(icon, self)
            tray.setToolTip("Intune Manager")
            tray.show()
            self._tray_icon = tray
        else:
            self._tray_icon = None
        self._command_palette = CommandPalette(
            self._command_registry,
            executor=self._execute_command,
            parent=self,
        )
        self._theme_manager.themeChanged.connect(self._apply_theme)
        self._apply_theme()

    def _populate_navigation(self) -> None:
        if self._ui_context is None:
            # Ensure components initialised before populating navigation.
            self._ui_context = UIContext(
                show_notification=self.show_notification,
                set_busy=self.set_busy,
                clear_busy=self.clear_busy,
                run_async=self.run_async,
                command_registry=self._command_registry,
                theme_manager=self._theme_manager,
                show_banner=self.show_banner,
                clear_banner=self.clear_banner,
            )

        self._nav_list.clear()

        while self._stack.count():
            widget = self._stack.widget(0)
            self._stack.removeWidget(widget)
            widget.deleteLater()

        self._pages.clear()
        self._dashboard_widget = None

        for index, item in enumerate(self.NAV_ITEMS):
            list_item = QListWidgetItem(item.icon or QIcon(), item.label)
            list_item.setData(Qt.ItemDataRole.UserRole, item.key)
            self._nav_list.addItem(list_item)

            page = self._build_page_for_item(item)
            self._pages[item.key] = page
            self._stack.addWidget(page)
            if index == 0:
                self._nav_list.setCurrentRow(0)
                self._stack.setCurrentIndex(0)

    def _register_shortcuts(self) -> None:
        self._shortcut_definitions = self._build_shortcut_definitions()

        for shortcut in self._shortcuts:
            shortcut.setParent(None)
        self._shortcuts.clear()

        for definition in self._shortcut_definitions:
            for sequence in definition.sequences:
                key_sequence = QKeySequence(sequence)
                if key_sequence == QKeySequence():
                    continue
                shortcut = QShortcut(key_sequence, self)
                shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
                shortcut.activated.connect(definition.callback)
                self._shortcuts.append(shortcut)

        if self._shortcuts_dialog is not None:
            self._shortcuts_dialog.set_shortcuts(self._shortcut_definitions)

    def _register_commands(self) -> None:
        for definition in self._shortcut_definitions:
            if not definition.show_in_palette:
                continue
            shortcut_text = definition.primary_sequence()
            self._command_registry.register(
                CommandAction(
                    id=definition.id,
                    title=definition.title,
                    callback=definition.callback,
                    category=definition.category,
                    description=definition.description,
                    shortcut=shortcut_text,
                ),
            )

    def _build_page_for_item(self, item: NavigationItem) -> QWidget:
        if item.key == "dashboard":
            if self._ui_context is None:
                raise RuntimeError(
                    "UI context not initialised before dashboard creation"
                )
            dashboard = DashboardWidget(
                self._services,
                context=self._ui_context,
                parent=self._stack,
            )
            self._dashboard_widget = dashboard
            return dashboard
        if item.key == "devices":
            if self._ui_context is None:
                raise RuntimeError(
                    "UI context not initialised before device view creation"
                )
            return DevicesWidget(
                self._services,
                context=self._ui_context,
                parent=self._stack,
            )
        if item.key == "applications":
            if self._ui_context is None:
                raise RuntimeError(
                    "UI context not initialised before applications view creation"
                )
            return ApplicationsWidget(
                self._services,
                context=self._ui_context,
                parent=self._stack,
            )
        if item.key == "groups":
            if self._ui_context is None:
                raise RuntimeError(
                    "UI context not initialised before groups view creation"
                )
            return GroupsWidget(
                self._services,
                context=self._ui_context,
                parent=self._stack,
            )
        if item.key == "assignments":
            if self._ui_context is None:
                raise RuntimeError(
                    "UI context not initialised before assignments view creation"
                )
            return AssignmentsWidget(
                self._services,
                context=self._ui_context,
                parent=self._stack,
            )
        if item.key == "reports":
            if self._ui_context is None:
                raise RuntimeError(
                    "UI context not initialised before reports view creation"
                )
            return ReportsWidget(
                self._services,
                context=self._ui_context,
                parent=self._stack,
            )
        if item.key == "settings":
            page = PageScaffold(
                "Settings & Diagnostics",
                subtitle=(
                    "Manage tenant credentials, validate Microsoft Graph permissions, and reset configuration."
                ),
                parent=self._stack,
            )
            settings_page = SettingsPage(
                diagnostics=self._services.diagnostics if self._services else None,
                services=self._services,
                parent=page,
            )
            page.add_body_widget(settings_page, stretch=1)
            page.body_layout.addStretch()
            self._settings_page = settings_page
            return page
        return self._create_placeholder_page(item)

    def _build_shortcut_definitions(self) -> list[ShortcutDefinition]:
        shortcuts = [
            ShortcutDefinition(
                id="command.palette",
                title="Open command palette",
                sequences=("Ctrl+K", "Meta+K"),
                callback=self._open_command_palette,
                category="Global",
                description="Search for commands, navigation targets, and quick actions.",
                show_in_palette=False,
            ),
            ShortcutDefinition(
                id="help.shortcuts",
                title="Show keyboard shortcuts",
                sequences=("Ctrl+/", "Meta+/", "F1"),
                callback=self._show_shortcuts_overlay,
                category="Help",
                description="Display the shortcut reference overlay.",
            ),
            ShortcutDefinition(
                id="global.refresh",
                title="Refresh data",
                sequences=("Ctrl+R", "Meta+R", "F5"),
                callback=self._refresh_active_view,
                category="Global",
                description="Refresh the active module or start a tenant sync.",
            ),
            ShortcutDefinition(
                id="global.focus-search",
                title="Focus search",
                sequences=("Ctrl+F", "Meta+F"),
                callback=self._focus_active_search,
                category="Global",
                description="Focus the search field in the current module.",
            ),
        ]
        shortcuts.extend(self._build_navigation_shortcuts())
        return shortcuts

    def _build_navigation_shortcuts(self) -> list[ShortcutDefinition]:
        shortcuts: list[ShortcutDefinition] = []
        for index, item in enumerate(self.NAV_ITEMS, start=1):
            sequences = (f"Ctrl+{index}", f"Meta+{index}")
            shortcuts.append(
                ShortcutDefinition(
                    id=f"nav.{item.key}",
                    title=f"Go to {item.label}",
                    sequences=sequences,
                    callback=lambda key=item.key: self._navigate_to_nav_item(key),
                    category="Navigation",
                    description=f"Switch to the {item.label} module.",
                ),
            )
        return shortcuts

    def _connect_navigation(self) -> None:
        self._nav_list.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._nav_list.currentItemChanged.connect(self._handle_nav_changed)

    def _connect_services(self) -> None:
        if self._services.sync:
            logger.debug("SyncService available for MainWindow wiring")
            self._subscriptions.append(
                self._services.sync.progress.subscribe(self._handle_sync_progress),
            )
            self._subscriptions.append(
                self._services.sync.errors.subscribe(self._handle_sync_error),
            )

    def _evaluate_onboarding_state(self) -> None:
        try:
            status = detect_first_run()
        except Exception:  # noqa: BLE001 - defensive startup logging
            logger.exception("Failed to evaluate first-run state")
            return

        self._first_run_status = status
        logger.debug(
            "Evaluated onboarding state",
            first_run=status.is_first_run,
            missing_settings=status.missing_settings,
            has_token_cache=status.has_token_cache,
            token_cache=str(status.token_cache_path),
        )

        if not status.is_first_run:
            return

        self._set_banner_action(self._open_onboarding_setup)
        self.show_banner(
            (
                "Welcome to Intune Manager. Complete the tenant configuration and sign in to "
                "start managing Intune resources."
            ),
            level=ToastLevel.WARNING,
            action_label="Start setup",
        )

    def _display_safe_mode_banner(self) -> None:
        if not safe_mode_enabled():
            return
        reason = safe_mode_reason()
        message = (
            "Intune Manager is running in Safe Mode. Background diagnostics and "
            "automatic cache refresh are paused until you relaunch normally."
        )
        if reason:
            message = f"{message}\nReason: {reason}"
        action_label = None
        if self._services.diagnostics is not None:
            action_label = "Clear caches"
            self._set_banner_action(self._purge_caches_from_safe_mode)
        else:
            self._set_banner_action(None)
        self.show_banner(message, level=ToastLevel.WARNING, action_label=action_label)

    def _display_previous_crash_notice(self) -> None:
        info = self._startup_crash_info
        if not info:
            return

        timestamp = info.get("timestamp")
        readable = timestamp or "unknown time"
        if timestamp:
            try:
                readable = (
                    datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    .astimezone()
                    .strftime("%Y-%m-%d %H:%M:%S %Z")
                )
            except ValueError:
                readable = timestamp

        exception_type = info.get("exception_type", "Unhandled exception")
        message = (
            "The previous session ended unexpectedly. "
            f"Crash captured at {readable} ({exception_type})."
        )
        logger.warning(
            "Previous session crashed",
            exception_type=exception_type,
            crash_timestamp=timestamp,
            crash_report=info.get("report_path"),
        )
        self.show_notification(message, level=ToastLevel.ERROR, duration_ms=8000)

        report_path = info.get("report_path")
        self._crash_report_path = Path(report_path) if report_path else None

        if self._alert_banner and not self._alert_banner.isVisible():
            banner_message = (
                f"Previous session crashed at {readable}. Review the log for details."
            )
            action_label = "Open crash log" if self._crash_report_path else None
            if action_label:
                self._set_banner_action(self._open_crash_report)
            else:
                self._set_banner_action(None)
            self.show_banner(
                banner_message,
                level=ToastLevel.ERROR,
                action_label=action_label,
            )

        self._startup_crash_info = None

    def _restore_window_preferences(self) -> None:
        geometry = self._settings_store.value("window/geometry")
        if isinstance(geometry, (bytes, bytearray)):
            self.restoreGeometry(geometry)

        state = self._settings_store.value("window/state")
        if isinstance(state, (bytes, bytearray)):
            self.restoreState(state)

        theme_name = self._settings_store.value("theme/name", "light")
        if isinstance(theme_name, str):
            self._theme_manager.set_theme(theme_name)
        else:
            self._theme_manager.set_theme("light")
        self._apply_theme()

    def _persist_window_state(self) -> None:
        self._settings_store.setValue("window/geometry", self.saveGeometry())
        self._settings_store.setValue("window/state", self.saveState())
        self._settings_store.setValue("theme/name", self._theme_manager.current.name)

    def _disconnect_services(self) -> None:
        while self._subscriptions:
            unsubscribe = self._subscriptions.pop()
            try:
                unsubscribe()
            except Exception:  # pragma: no cover - best effort cleanup
                logger.exception("Failed to unsubscribe service callback")

    def _apply_theme(self, *_: object) -> None:
        self.setStyleSheet(self._theme_manager.base_stylesheet())

    # --------------------------------------------------------------- UI helpers

    def run_async(self, coro: Awaitable[object]) -> None:
        self._bridge.run_coroutine(coro)

    def set_busy(self, message: str | None = None) -> None:
        display = message or self._busy_default_message
        if self._busy_overlay:
            self._busy_overlay.show_overlay(display)
        self.statusBar().showMessage(display)

    def set_busy_message(self, message: str) -> None:
        if self._busy_overlay and self._busy_overlay.isVisible():
            self._busy_overlay.set_message(message)
        self.statusBar().showMessage(message)

    def clear_busy(self) -> None:
        if self._busy_overlay:
            self._busy_overlay.hide_overlay()
        self.statusBar().showMessage(self._status_default_message)

    def show_notification(
        self,
        message: str,
        *,
        level: ToastLevel = ToastLevel.INFO,
        duration_ms: int = 4500,
    ) -> None:
        if self._toast_manager:
            self._toast_manager.show_toast(
                message, level=level, duration_ms=duration_ms
            )
        self.statusBar().showMessage(message, 3000)
        if self._tray_icon:
            notify_levels = {ToastLevel.ERROR, ToastLevel.WARNING}
            if not self.isActiveWindow():
                notify_levels.add(ToastLevel.SUCCESS)
            if level in notify_levels:
                icon = QSystemTrayIcon.MessageIcon.Warning
                if level is ToastLevel.ERROR:
                    icon = QSystemTrayIcon.MessageIcon.Critical
                elif level is ToastLevel.SUCCESS:
                    icon = QSystemTrayIcon.MessageIcon.Information
                self._tray_icon.showMessage(
                    "Intune Manager", message, icon, duration_ms
                )

    def show_banner(
        self,
        message: str,
        level: ToastLevel = ToastLevel.INFO,
        *,
        action_label: str | None = None,
    ) -> None:
        if self._alert_banner:
            self._alert_banner.display(message, level=level, action_label=action_label)

    def clear_banner(self) -> None:
        if self._alert_banner:
            self._alert_banner.clear()

    def _set_banner_action(self, action: Callable[[], None] | None) -> None:
        self._banner_action = action

    def _handle_banner_action_triggered(self) -> None:
        if self._banner_action is None:
            return
        try:
            self._banner_action()
        except Exception:  # noqa: BLE001 - UI action safety
            logger.exception("Banner action failed")
            self.show_notification(
                "Setup action failed to launch.",
                level=ToastLevel.ERROR,
                duration_ms=6000,
            )

    def _handle_banner_dismissed(self) -> None:
        self._banner_action = None

    def _purge_caches_from_safe_mode(self) -> None:
        diagnostics = self._services.diagnostics if self._services else None
        if diagnostics is None:
            self.show_notification(
                "Diagnostics service unavailable; cannot clear caches.",
                level=ToastLevel.ERROR,
            )
            return
        self.set_busy("Clearing cached Graph data…")
        try:
            diagnostics.clear_all_caches()
            diagnostics.purge_attachments()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to purge caches from safe mode banner")
            self.show_notification(
                "Failed to clear cached data.",
                level=ToastLevel.ERROR,
            )
        else:
            self.show_notification(
                "All cached data purged successfully.",
                level=ToastLevel.SUCCESS,
            )
        finally:
            self.clear_busy()

    def _open_crash_report(self) -> None:
        if not self._crash_report_path:
            self.show_notification(
                "Crash log is no longer available.",
                level=ToastLevel.WARNING,
            )
            return
        path = self._crash_report_path
        if not path.exists():
            self.show_notification(
                f"Crash log missing at {path}.",
                level=ToastLevel.WARNING,
            )
            return
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        if not opened:
            self.show_notification(
                "Unable to open crash log.",
                level=ToastLevel.ERROR,
            )

    # --------------------------------------------------------------- Commands

    def _open_command_palette(self) -> None:
        if self._command_palette:
            self._command_palette.open_palette()

    def _execute_command(self, action: CommandAction) -> None:
        try:
            result = action.callback()
            if inspect.isawaitable(result):
                self._bridge.run_coroutine(result)  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001
            logger.exception("Command execution failed", command=action.id)
            self.show_notification(
                f"Command failed: {action.title}",
                level=ToastLevel.ERROR,
                duration_ms=6000,
            )

    def _show_shortcuts_overlay(self) -> None:
        if self._shortcuts_dialog is None:
            self._shortcuts_dialog = ShortcutHelpDialog(
                self._shortcut_definitions, parent=self
            )
        else:
            self._shortcuts_dialog.set_shortcuts(self._shortcut_definitions)
        self._shortcuts_dialog.show()
        self._shortcuts_dialog.raise_()
        self._shortcuts_dialog.activateWindow()

    def _refresh_active_view(self) -> None:
        page = self._current_page()
        if page is None:
            return

        for attribute in ("trigger_refresh", "refresh", "start_refresh"):
            handler = getattr(page, attribute, None)
            if callable(handler):
                try:
                    result = handler()
                    if inspect.isawaitable(result):
                        self._bridge.run_coroutine(result)  # type: ignore[arg-type]
                    return
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Refresh handler failed", widget=type(page).__name__
                    )
                    self.show_notification(
                        "Refresh failed to start.",
                        level=ToastLevel.ERROR,
                        duration_ms=6000,
                    )
                    return
        self._start_global_sync()

    def _start_global_sync(self) -> None:
        if self._sync_in_progress:
            self.show_notification(
                "A tenant sync is already running.",
                level=ToastLevel.INFO,
                duration_ms=3500,
            )
            return
        if self._services.sync is None:
            self.show_notification(
                "Sync service not configured yet.",
                level=ToastLevel.WARNING,
                duration_ms=5000,
            )
            return
        self._sync_in_progress = True
        self.set_busy("Refreshing tenant data…")
        self._bridge.run_coroutine(self._services.sync.refresh_all(force=True))

    def _focus_active_search(self) -> None:
        page = self._current_page()
        if page is None:
            return
        handler = getattr(page, "focus_search", None)
        if callable(handler):
            try:
                handler()
                return
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Focus search handler failed", widget=type(page).__name__
                )
                self.show_notification(
                    "Search field failed to focus.",
                    level=ToastLevel.ERROR,
                    duration_ms=4000,
                )
                return
        self.show_notification(
            "No searchable field on this view.",
            level=ToastLevel.INFO,
            duration_ms=3500,
        )

    def _open_onboarding_setup(self) -> None:
        self._navigate_to_nav_item("settings")
        if self._settings_page is not None:
            self._settings_page.launch_setup_wizard()
        else:
            self.show_notification(
                "Open the Settings tab to configure your tenant and sign in.",
                level=ToastLevel.INFO,
                duration_ms=6000,
            )

    def _navigate_to_nav_item(self, key: str) -> None:
        for index in range(self._nav_list.count()):
            item = self._nav_list.item(index)
            if item is None:
                continue
            if item.data(Qt.ItemDataRole.UserRole) == key:
                self._nav_list.setCurrentRow(index)
                return

    # -------------------------------------------------------------- Service glue

    def _handle_sync_progress(self, event: SyncProgressEvent) -> None:
        phase = event.phase.replace("_", " ").title()
        total = max(event.total, 1)
        message = f"Refreshing {phase} ({event.completed}/{total})"
        self.set_busy(message)
        if event.completed >= total:
            self._sync_in_progress = False
            self.clear_busy()
            self.show_notification("Tenant data refreshed", level=ToastLevel.SUCCESS)

    def _handle_sync_error(self, event: ServiceErrorEvent) -> None:
        self.clear_busy()
        detail = str(event.error)
        self._sync_in_progress = False
        self.show_notification(
            f"Sync failed: {detail}",
            level=ToastLevel.ERROR,
            duration_ms=8000,
        )

    # ----------------------------------------------------------------- Helpers

    def _current_page(self) -> QWidget | None:
        return self._stack.currentWidget()

    def _create_placeholder_page(self, item: NavigationItem) -> QWidget:
        page = PageScaffold(
            item.label,
            subtitle="Placeholder view — functionality coming in later Phase 6 tasks.",
        )

        message = QLabel(
            "This module is not yet implemented. Continue through Phase 6 to unlock full "
            "cross-platform Intune management workflows.",
        )
        message.setWordWrap(True)
        message.setProperty("class", "page-subtitle")

        page.add_body_widget(message)
        page.body_layout.addStretch()
        return page

    def _handle_nav_changed(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            return
        key = current.data(Qt.ItemDataRole.UserRole)
        logger.debug("Navigation changed", destination=key)
        if self._busy_overlay and self._busy_overlay.isVisible():
            return
        self.statusBar().showMessage(f"{current.text()} ready", 2000)

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        self._persist_window_state()
        self._disconnect_services()
        super().closeEvent(event)

    @property
    def ui_context(self) -> UIContext:
        if self._ui_context is None:
            raise RuntimeError("UI context not initialised")
        return self._ui_context

    @property
    def first_run_status(self) -> FirstRunStatus | None:
        return self._first_run_status


__all__ = ["MainWindow", "NavigationItem"]
