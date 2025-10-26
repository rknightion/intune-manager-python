from __future__ import annotations

from datetime import UTC, datetime

import pytest

from intune_manager.services import ServiceRegistry
from intune_manager.ui.components import (
    CommandRegistry,
    ThemeManager,
    ToastLevel,
    UIContext,
)
from intune_manager.ui.dashboard.controller import (
    AnalyticsSummary,
    DashboardController,
    DashboardSnapshot,
    ResourceMetric,
    TenantStatus,
)
from intune_manager.ui.dashboard.widgets import DashboardWidget


def _make_context():
    notifications: list[tuple[str, ToastLevel, int]] = []
    busy_events: list[tuple[str, str | None]] = []
    banners: list[tuple[str, ToastLevel | None]] = []
    async_calls: list[object] = []

    def show_notification(
        message: str, level: ToastLevel, duration_ms: int | None
    ) -> None:
        notifications.append((message, level, duration_ms))

    def set_busy(message: str | None, *, blocking: bool = True) -> None:
        tag = f"{message} (non-blocking)" if not blocking else message
        busy_events.append(("set", tag))

    def clear_busy() -> None:
        busy_events.append(("clear", None))

    def run_async(coro) -> None:
        async_calls.append(coro)

    def show_banner(message: str, level: ToastLevel, **_: object) -> None:
        banners.append((message, level))

    def clear_banner() -> None:
        banners.append(("clear", None))

    context = UIContext(
        show_notification=show_notification,
        set_busy=set_busy,
        clear_busy=clear_busy,
        run_async=run_async,
        command_registry=CommandRegistry(),
        theme_manager=ThemeManager(),
        show_banner=show_banner,
        clear_banner=clear_banner,
    )
    return context, notifications, busy_events, banners


@pytest.mark.usefixtures("qt_app")
def test_dashboard_refresh_snapshot_updates_metrics(
    monkeypatch: pytest.MonkeyPatch, qtbot
):
    context, notifications, busy_events, banners = _make_context()

    first_snapshot = DashboardSnapshot(
        tenant=TenantStatus(
            tenant_id="contoso.onmicrosoft.com",
            client_id="client-id",
            configured=True,
            signed_in=True,
            account_name="Admin",
            account_upn="admin@contoso.com",
            missing_scopes=["Device.Read.All"],
        ),
        resources=[
            ResourceMetric(
                key="devices",
                label="Managed devices",
                count=125,
                stale=False,
                available=True,
                last_refresh=datetime.now(UTC),
            ),
            ResourceMetric(
                key="applications",
                label="Applications",
                count=None,
                stale=None,
                available=False,
                warning="Applications service not configured",
            ),
        ],
        warnings=["Applications service not configured"],
        analytics=AnalyticsSummary(
            compliance={"Compliant": 110, "Non-compliant": 15},
            assignment_intents={"required": 3, "available": 2},
        ),
    )

    monkeypatch.setattr(
        DashboardController,
        "collect_snapshot",
        lambda self, tenant_id=None: first_snapshot,
    )

    widget = DashboardWidget(ServiceRegistry(), context=context)
    qtbot.addWidget(widget)
    widget.show()

    devices_card = widget._metric_cards["devices"]  # noqa: SLF001 - internal wiring under test
    apps_card = widget._metric_cards["applications"]  # noqa: SLF001

    assert devices_card.value_label.text() == "125"
    assert apps_card.status_label.text() == "Not configured"
    assert widget._warnings_list.count() == 1  # noqa: SLF001
    assert widget._warnings_list.item(0).text() == "Applications service not configured"  # noqa: SLF001
    assert banners and banners[-1][0] == "Applications service not configured"
    assert widget._warnings_list.isVisible()  # noqa: SLF001
    assert widget._warnings_list.count() == 1  # noqa: SLF001
    assert banners and banners[-1][0] == "Applications service not configured"

    refreshed_snapshot = DashboardSnapshot(
        tenant=first_snapshot.tenant,
        resources=[
            ResourceMetric(
                key="devices",
                label="Managed devices",
                count=140,
                stale=False,
                available=True,
                last_refresh=datetime.now(UTC),
            ),
            ResourceMetric(
                key="applications",
                label="Applications",
                count=42,
                stale=False,
                available=True,
                last_refresh=datetime.now(UTC),
            ),
        ],
        warnings=[],
        analytics=AnalyticsSummary(
            compliance={"Compliant": 120, "Non-compliant": 20},
            assignment_intents={"required": 4, "available": 3},
        ),
    )

    monkeypatch.setattr(
        DashboardController,
        "collect_snapshot",
        lambda self, tenant_id=None: refreshed_snapshot,
    )
    widget.refresh_snapshot()

    assert devices_card.value_label.text() == "140"
    assert widget._warnings_list.isVisible() is False  # noqa: SLF001
    assert banners[-1] == ("clear", None)
    assert not notifications, "Passive refresh should not emit notifications"
    assert busy_events == [], (
        "Snapshot refresh without sync should not toggle busy state"
    )
