from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict

from PySide6.QtCore import Qt, QSize, QSettings
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QWidget,
)

from intune_manager.services import ServiceErrorEvent, ServiceRegistry, SyncProgressEvent
from intune_manager.ui.components import (
    BusyOverlay,
    PageScaffold,
    TenantBadge,
    ThemeManager,
    ToastLevel,
    ToastManager,
)
from intune_manager.ui.dashboard import DashboardWidget
from intune_manager.utils import get_logger
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
        NavigationItem("groups", "Groups"),
        NavigationItem("assignments", "Assignments"),
        NavigationItem("reports", "Reports"),
        NavigationItem("settings", "Settings"),
    )

    def __init__(
        self,
        services: ServiceRegistry,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._services = services
        self._bridge = AsyncBridge()
        self._stack = QStackedWidget()
        self._nav_list = QListWidget()
        self._pages: Dict[str, QWidget] = {}
        self._settings_store = QSettings("IntuneManager", "IntuneManagerApp")
        self._theme_manager = ThemeManager()
        self._toast_manager: ToastManager | None = None
        self._busy_overlay: BusyOverlay | None = None
        self._tenant_badge = TenantBadge()
        self._status_default_message = "Ready"
        self._busy_default_message = "Working…"
        self._subscriptions: list[Callable[[], None]] = []

        self._configure_window()
        self._build_layout()
        self._initialize_components()
        self._connect_navigation()
        self._connect_services()
        self._restore_window_preferences()

    # ------------------------------------------------------------------ Setup

    def _configure_window(self) -> None:
        self.setWindowTitle("Intune Manager")
        self.resize(1280, 820)
        self.setMinimumSize(QSize(960, 640))
        status = QStatusBar()
        status.setObjectName("MainStatusBar")
        status.setSizeGripEnabled(False)
        status.showMessage(self._status_default_message)
        status.addPermanentWidget(self._tenant_badge)
        self.setStatusBar(status)

    def _build_layout(self) -> None:
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self._nav_list.setObjectName("NavigationList")
        self._nav_list.setMaximumWidth(220)
        self._nav_list.setSpacing(2)
        self._nav_list.setAlternatingRowColors(True)
        self._nav_list.setSelectionMode(QListWidget.SingleSelection)
        self._nav_list.setSizePolicy(
            QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding),
        )

        for index, item in enumerate(self.NAV_ITEMS):
            list_item = QListWidgetItem(item.icon or QIcon(), item.label)
            list_item.setData(Qt.ItemDataRole.UserRole, item.key)
            self._nav_list.addItem(list_item)
            if item.key == "dashboard":
                page = DashboardWidget(
                    self._services,
                    parent=self._stack,
                    host=self,
                )
            else:
                page = self._create_placeholder_page(item)
            self._pages[item.key] = page
            self._stack.addWidget(page)
            if index == 0:
                self._nav_list.setCurrentRow(0)
                self._stack.setCurrentIndex(0)

        layout.addWidget(self._nav_list)
        layout.addWidget(self._stack, stretch=1)
        self.setCentralWidget(central)

    def _initialize_components(self) -> None:
        central = self.centralWidget()
        if central is None:
            return
        self._busy_overlay = BusyOverlay(central)
        self._toast_manager = ToastManager(central, theme=self._theme_manager)
        self._theme_manager.themeChanged.connect(self._apply_theme)
        self._apply_theme()

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

    def _restore_window_preferences(self) -> None:
        geometry = self._settings_store.value("window/geometry")
        if isinstance(geometry, (bytes, bytearray)):
            self.restoreGeometry(geometry)

        state = self._settings_store.value("window/state")
        if isinstance(state, (bytes, bytearray)):
            self.restoreState(state)

        theme_name = self._settings_store.value("theme/name", "light")
        if isinstance(theme_name, str) and theme_name in {"light", "dark"}:
            self._theme_manager.set_theme(theme_name)
        else:
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
            self._toast_manager.show_toast(message, level=level, duration_ms=duration_ms)
        self.statusBar().showMessage(message, 3000)

    # -------------------------------------------------------------- Service glue

    def _handle_sync_progress(self, event: SyncProgressEvent) -> None:
        phase = event.phase.replace("_", " ").title()
        total = max(event.total, 1)
        message = f"Refreshing {phase} ({event.completed}/{total})"
        self.set_busy(message)
        if event.completed >= total:
            self.clear_busy()
            self.show_notification("Tenant data refreshed", level=ToastLevel.SUCCESS)

    def _handle_sync_error(self, event: ServiceErrorEvent) -> None:
        self.clear_busy()
        detail = str(event.error)
        self.show_notification(
            f"Sync failed: {detail}",
            level=ToastLevel.ERROR,
            duration_ms=8000,
        )

    # ----------------------------------------------------------------- Helpers

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


__all__ = ["MainWindow", "NavigationItem"]
