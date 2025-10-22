from __future__ import annotations

from typing import Dict

from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from intune_manager.services import ServiceRegistry
from intune_manager.ui.components import PageScaffold, ToastLevel
from intune_manager.ui.dashboard.controller import (
    DashboardController,
    DashboardSnapshot,
    ResourceMetric,
)
from intune_manager.utils.asyncio import AsyncBridge


class MetricCard(QFrame):
    """Card displaying a single metric summary."""

    def __init__(self, title: str, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        self.title_label = QLabel(title)
        self.title_label.setProperty("class", "card-title")
        title_font = self.title_label.font()
        title_font.setPointSizeF(title_font.pointSizeF() + 1)
        title_font.setWeight(600)
        self.title_label.setFont(title_font)

        self.value_label = QLabel("—")
        value_font = self.value_label.font()
        value_font.setPointSizeF(value_font.pointSizeF() + 6)
        value_font.setWeight(700)
        self.value_label.setFont(value_font)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: palette(mid);")

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.status_label)

    def update_metric(self, metric: ResourceMetric) -> None:
        if metric.count is None:
            self.value_label.setText("—")
        else:
            self.value_label.setText(f"{metric.count:,}")

        if not metric.available:
            self.status_label.setText("Not configured")
            self.status_label.setStyleSheet("color: palette(mid);")
            return

        if metric.warning:
            self.status_label.setText(metric.warning)
            self.status_label.setStyleSheet("color: #c92a2a;")
            return

        if metric.stale:
            self.status_label.setText("Refresh recommended")
            self.status_label.setStyleSheet("color: #c15d12;")
        else:
            self.status_label.setText("Up to date")
            self.status_label.setStyleSheet("color: #1b8651;")


class DashboardWidget(PageScaffold):
    """Dashboard overview widget combining metrics and quick actions."""

    def __init__(
        self,
        services: ServiceRegistry,
        *,
        parent: QWidget | None = None,
        host: QWidget | None = None,
    ) -> None:
        self._refresh_button = QPushButton("Refresh tenant data")
        self._refresh_button.setObjectName("DashboardRefreshButton")

        super().__init__(
            "Dashboard",
            subtitle=(
                "Track tenant health at a glance. Refresh cached data or navigate to modules for "
                "detailed management workflows."
            ),
            actions=[self._refresh_button],
            parent=parent,
        )

        self._services = services
        self._host = host
        self._controller = DashboardController(services)
        self._bridge = AsyncBridge()
        self._bridge.task_completed.connect(self._handle_async_result)
        self._pending_action: str | None = None
        self._latest_snapshot: DashboardSnapshot | None = None

        self._metrics_frame = QWidget()
        self._metrics_layout = QGridLayout(self._metrics_frame)
        self._metrics_layout.setContentsMargins(0, 0, 0, 0)
        self._metrics_layout.setHorizontalSpacing(16)
        self._metrics_layout.setVerticalSpacing(16)

        self._metric_cards: Dict[str, MetricCard] = {}

        self._summary_label = QLabel()
        self._summary_label.setWordWrap(True)
        self._summary_label.setProperty("class", "page-subtitle")

        self._warnings_list = QListWidget()
        self._warnings_list.setObjectName("DashboardWarnings")
        self._warnings_list.setVisible(False)

        self.body_layout.addWidget(self._summary_label)
        self.body_layout.addWidget(self._metrics_frame)
        self.body_layout.addWidget(self._warnings_list)
        self.body_layout.addStretch()

        self._refresh_button.clicked.connect(self._handle_refresh_clicked)

        self._ensure_metric_cards()
        self.refresh_snapshot()

    # ------------------------------------------------------------------ UI setup

    def _ensure_metric_cards(self) -> None:
        labels = {
            "devices": "Managed devices",
            "applications": "Applications",
            "groups": "Groups",
            "filters": "Assignment filters",
            "configurations": "Configurations",
            "audit": "Audit events",
        }

        for index, (key, label) in enumerate(labels.items()):
            card = MetricCard(label, parent=self._metrics_frame)
            self._metric_cards[key] = card
            row = index // 3
            column = index % 3
            self._metrics_layout.addWidget(card, row, column)

    # ----------------------------------------------------------------- Snapshot

    def refresh_snapshot(self) -> None:
        snapshot = self._controller.collect_snapshot()
        self._latest_snapshot = snapshot
        self._render_snapshot(snapshot)

    def _render_snapshot(self, snapshot: DashboardSnapshot) -> None:
        available = [
            metric for metric in snapshot.resources if metric.available and metric.count is not None
        ]
        total_items = sum(metric.count for metric in available if metric.count is not None)
        stale_count = sum(1 for metric in snapshot.resources if metric.stale)

        self._summary_label.setText(
            f"Cached items: {total_items:,} across {len(available)} resource types. "
            f"{'Stale caches detected — consider refreshing.' if stale_count else 'All caches look fresh.'}"
        )

        for metric in snapshot.resources:
            card = self._metric_cards.get(metric.key)
            if card is None:
                continue
            card.update_metric(metric)

        self._warnings_list.clear()
        if snapshot.warnings:
            for warning in snapshot.warnings:
                QListWidgetItem(warning, self._warnings_list)
            self._warnings_list.setVisible(True)
        else:
            self._warnings_list.setVisible(False)

    # ----------------------------------------------------------------- Actions

    def _handle_refresh_clicked(self) -> None:
        if self._services.sync is None:
            self._notify("Sync service not configured. Configure services in settings.", ToastLevel.WARNING)
            return
        if self._pending_action is not None:
            return  # refresh already in flight

        self._pending_action = "sync"
        self._refresh_button.setEnabled(False)
        if hasattr(self._host, "set_busy"):
            getattr(self._host, "set_busy")("Starting tenant sync…")
        self._notify("Refreshing tenant data…", ToastLevel.INFO)
        self._bridge.run_coroutine(self._controller.refresh_all(force=True))

    def _handle_async_result(self, result: object, error: object) -> None:
        action = self._pending_action
        if action is None:
            return
        self._pending_action = None
        self._refresh_button.setEnabled(True)
        if hasattr(self._host, "clear_busy"):
            getattr(self._host, "clear_busy")()

        if action == "sync":
            if error:
                self._notify(f"Tenant refresh failed: {error}", ToastLevel.ERROR)
                return
            self._notify("Tenant data refreshed", ToastLevel.SUCCESS)
            self.refresh_snapshot()

    # ---------------------------------------------------------------- Utilities

    def _notify(self, message: str, level: ToastLevel) -> None:
        if hasattr(self._host, "show_notification"):
            getattr(self._host, "show_notification")(message, level=level)
        else:
            self._summary_label.setText(message)


__all__ = ["DashboardWidget"]
