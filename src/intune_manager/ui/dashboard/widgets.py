from __future__ import annotations

from typing import Callable, Dict

from PySide6.QtCore import Qt
from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QPieSeries,
    QValueAxis,
)
from PySide6.QtGui import QCloseEvent, QFont, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from intune_manager.services import ServiceRegistry
from intune_manager.ui.components import (
    CommandAction,
    PageScaffold,
    ToastLevel,
    UIContext,
)
from intune_manager.ui.dashboard.controller import DashboardController, DashboardSnapshot, ResourceMetric, TenantStatus
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
        title_font.setWeight(QFont.Weight.DemiBold)
        self.title_label.setFont(title_font)

        self.value_label = QLabel("—")
        value_font = self.value_label.font()
        value_font.setPointSizeF(value_font.pointSizeF() + 6)
        value_font.setWeight(QFont.Weight.Bold)
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


_STATUS_COLORS: Dict[ToastLevel, tuple[str, str, str]] = {
    ToastLevel.INFO: ("#1d4ed8", "rgba(59, 130, 246, 0.12)", "rgba(59, 130, 246, 0.3)"),
    ToastLevel.SUCCESS: ("#15803d", "rgba(34, 197, 94, 0.15)", "rgba(34, 197, 94, 0.35)"),
    ToastLevel.WARNING: ("#b45309", "rgba(249, 115, 22, 0.18)", "rgba(249, 115, 22, 0.35)"),
    ToastLevel.ERROR: ("#b91c1c", "rgba(239, 68, 68, 0.18)", "rgba(239, 68, 68, 0.35)"),
}


class StatusCard(QFrame):
    """Highlight tenant/auth status with contextual styling."""

    def __init__(self, title: str, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(6)

        self._title_label = QLabel(title)
        title_font = self._title_label.font()
        title_font.setWeight(QFont.Weight.DemiBold)
        self._title_label.setFont(title_font)

        self._state_label = QLabel()
        state_font = self._state_label.font()
        state_font.setPointSizeF(state_font.pointSizeF() + 4)
        state_font.setWeight(QFont.Weight.Bold)
        self._state_label.setFont(state_font)

        self._detail_label = QLabel()
        self._detail_label.setWordWrap(True)
        self._detail_label.setStyleSheet("color: palette(mid);")

        layout.addWidget(self._title_label)
        layout.addWidget(self._state_label)
        layout.addWidget(self._detail_label)

    def update_status(
        self,
        state: str,
        detail: str,
        *,
        level: ToastLevel = ToastLevel.INFO,
    ) -> None:
        color, background, border = _STATUS_COLORS.get(level, _STATUS_COLORS[ToastLevel.INFO])
        self._state_label.setText(state)
        self._detail_label.setText(detail)
        self.setStyleSheet(
            "QFrame#StatusCard {"
            f"  background-color: {background};"
            f"  border: 1px solid {border};"
            "  border-radius: 12px;"
            "}"
        )
        self._title_label.setStyleSheet(f"color: {color};")
        self._state_label.setStyleSheet(f"color: {color};")
        self._detail_label.setStyleSheet("color: palette(mid);")


class ComplianceChartView(QChartView):
    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(QChart(), parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setMinimumHeight(260)
        self.chart().setTitle("Device compliance")

    def update_data(self, distribution: Dict[str, int]) -> None:
        chart = self.chart()
        chart.removeAllSeries()
        chart.setTitle("Device compliance")
        if not distribution:
            chart.setTitle("Device compliance (no data)")
            chart.legend().setVisible(False)
            return

        series = QPieSeries()
        total = sum(distribution.values())
        if total == 0:
            chart.setTitle("Device compliance (no data)")
            chart.legend().setVisible(False)
            return

        for label, count in sorted(distribution.items(), key=lambda item: item[0]):
            percent = (count / total) * 100
            slice_label = f"{label} ({count}, {percent:.1f}%)"
            pie_slice = series.append(slice_label, count)
            pie_slice.setLabelVisible(True)

        chart.addSeries(series)
        chart.legend().setVisible(True)
        chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)


class AssignmentChartView(QChartView):
    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(QChart(), parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setMinimumHeight(260)
        self.chart().setTitle("Assignment intents")

    def update_data(self, intents: Dict[str, int]) -> None:
        chart = self.chart()
        chart.removeAllSeries()
        for axis in chart.axes():
            chart.removeAxis(axis)

        chart.setTitle("Assignment intents")
        if not intents:
            chart.setTitle("Assignment intents (no data)")
            return

        ordered = sorted(intents.items(), key=lambda item: item[0])
        categories = [label for label, _ in ordered]
        values = [count for _, count in ordered]

        series = QBarSeries()
        bar_set = QBarSet("Assignments")
        for value in values:
            bar_set.append(float(value))
        series.append(bar_set)
        series.setBarWidth(0.5)

        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setLabelFormat("%d")
        axis_y.setRange(0, max(values) if values else 1)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)

class DashboardWidget(PageScaffold):
    """Dashboard overview widget combining metrics and quick actions."""

    def __init__(
        self,
        services: ServiceRegistry,
        *,
        context: UIContext,
        parent: QWidget | None = None,
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
        self._context = context
        self._controller = DashboardController(services)
        self._bridge = AsyncBridge()
        self._bridge.task_completed.connect(self._handle_async_result)
        self._pending_action: str | None = None
        self._latest_snapshot: DashboardSnapshot | None = None
        self._command_unregister: Callable[[], None] | None = None

        self._status_frame = QWidget()
        self._status_layout = QHBoxLayout(self._status_frame)
        self._status_layout.setContentsMargins(0, 0, 0, 0)
        self._status_layout.setSpacing(12)

        self._tenant_card = StatusCard("Tenant configuration", parent=self._status_frame)
        self._auth_card = StatusCard("Authentication", parent=self._status_frame)
        self._status_layout.addWidget(self._tenant_card)
        self._status_layout.addWidget(self._auth_card)

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

        self._analytics_frame = QWidget()
        self._analytics_layout = QHBoxLayout(self._analytics_frame)
        self._analytics_layout.setContentsMargins(0, 0, 0, 0)
        self._analytics_layout.setSpacing(16)

        self._compliance_chart = ComplianceChartView(parent=self._analytics_frame)
        self._assignment_chart = AssignmentChartView(parent=self._analytics_frame)
        self._analytics_layout.addWidget(self._compliance_chart)
        self._analytics_layout.addWidget(self._assignment_chart)

        self.body_layout.addWidget(self._status_frame)
        self.body_layout.addWidget(self._summary_label)
        self.body_layout.addWidget(self._analytics_frame)
        self.body_layout.addWidget(self._metrics_frame)
        self.body_layout.addWidget(self._warnings_list)
        self.body_layout.addStretch()

        self._refresh_button.clicked.connect(self._handle_refresh_clicked)

        self._ensure_metric_cards()
        self.refresh_snapshot()
        self._register_commands()

    def _register_commands(self) -> None:
        action = CommandAction(
            id="tenant.refresh",
            title="Refresh tenant data",
            callback=self._start_refresh,
            category="Dashboard",
            description="Trigger a full sync across cached Intune resources.",
            shortcut="Ctrl+R",
        )
        self._command_unregister = self._context.command_registry.register(action)

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
        self._render_status_cards(snapshot.tenant)
        available = [
            metric
            for metric in snapshot.resources
            if metric.available and isinstance(metric.count, int)
        ]
        total_items = sum(metric.count for metric in available)
        stale_count = sum(1 for metric in snapshot.resources if metric.stale)

        self._summary_label.setText(
            f"Cached items: {total_items:,} across {len(available)} resource types. "
            f"{'Stale caches detected — consider refreshing.' if stale_count else 'All caches look fresh.'}"
        )

        self._compliance_chart.update_data(snapshot.analytics.compliance)
        self._assignment_chart.update_data(snapshot.analytics.assignment_intents)

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
            self._context.show_banner(snapshot.warnings[0], level=ToastLevel.WARNING)
        else:
            self._warnings_list.setVisible(False)
            self._context.clear_banner()

    # ----------------------------------------------------------------- Actions

    def _handle_refresh_clicked(self) -> None:
        self._start_refresh()

    def _handle_async_result(self, result: object, error: object) -> None:
        action = self._pending_action
        if action is None:
            return
        self._pending_action = None
        self._refresh_button.setEnabled(True)
        self._context.clear_busy()

        if action == "sync":
            if error:
                self._notify(f"Tenant refresh failed: {error}", ToastLevel.ERROR)
                return
            self._notify("Tenant data refreshed", ToastLevel.SUCCESS)
            self.refresh_snapshot()

    # ---------------------------------------------------------------- Utilities

    def _notify(self, message: str, level: ToastLevel) -> None:
        self._context.show_notification(message, level=level)

    def _start_refresh(self) -> None:
        if self._services.sync is None:
            self._notify(
                "Sync service not configured. Configure services in settings.",
                ToastLevel.WARNING,
            )
            return
        if self._pending_action is not None:
            return

        self._pending_action = "sync"
        self._refresh_button.setEnabled(False)
        self._context.set_busy("Starting tenant sync…")
        self._notify("Refreshing tenant data…", ToastLevel.INFO)
        self._bridge.run_coroutine(self._controller.refresh_all(force=True))

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        if self._command_unregister:
            self._command_unregister()
            self._command_unregister = None
        super().closeEvent(event)

    def _render_status_cards(self, status: TenantStatus) -> None:
        if status.configured:
            tenant_state = status.tenant_id or "Tenant configured"
            tenant_detail = (
                f"Client ID {status.client_id}" if status.client_id else "Tenant identifiers stored."
            )
            if status.missing_scopes:
                displayed = ", ".join(status.missing_scopes[:5])
                more = "…" if len(status.missing_scopes) > 5 else ""
                tenant_detail += f"\nMissing scopes: {displayed}{more}"
                tenant_level = ToastLevel.WARNING
            else:
                tenant_level = ToastLevel.SUCCESS
        else:
            tenant_state = "Not configured"
            tenant_detail = "Open Settings to provide tenant ID and client ID."
            tenant_level = ToastLevel.WARNING

        self._tenant_card.update_status(
            tenant_state,
            tenant_detail,
            level=tenant_level,
        )

        if status.signed_in:
            auth_state = status.account_name or "Signed in"
            detail = status.account_upn or "Access token cached."
            auth_level = ToastLevel.SUCCESS
        else:
            auth_state = "Not signed in"
            detail = "Use Settings → Test sign-in to authenticate."
            auth_level = ToastLevel.WARNING

        self._auth_card.update_status(auth_state, detail, level=auth_level)


__all__ = ["DashboardWidget"]
