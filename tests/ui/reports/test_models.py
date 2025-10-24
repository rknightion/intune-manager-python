from __future__ import annotations

from datetime import datetime

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from intune_manager.data.models.audit import AuditActor, AuditEvent, AuditResource
from intune_manager.ui.reports.models import AuditEventFilterProxyModel, AuditEventTableModel


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _sample_events() -> list[AuditEvent]:
    return [
        AuditEvent(
            id="1",
            activity="Device wipe initiated",
            activity_date_time=datetime(2024, 1, 1, 12, 0, 0),
            activity_result="success",
            category="Device",
            component_name="Device management",
            actor=AuditActor(user_principal_name="admin@contoso.com"),
            resources=[AuditResource(display_name="Device-01")],
        ),
        AuditEvent(
            id="2",
            activity="Policy assignment failed",
            activity_date_time=datetime(2024, 1, 2, 8, 30, 0),
            activity_result="failure",
            category="Configuration",
            component_name="Configuration policies",
            actor=AuditActor(service_principal_name="GraphApp"),
            resources=[AuditResource(display_name="Policy-Alpha")],
        ),
    ]


def test_table_model_exposes_event_data(qt_app: QApplication) -> None:  # noqa: ARG001 - fixture ensures Qt initialised
    model = AuditEventTableModel(_sample_events())
    assert model.rowCount() == 2
    assert model.columnCount() >= 5

    index = model.index(0, 0)
    display = model.data(index, Qt.ItemDataRole.DisplayRole)
    assert isinstance(display, str)
    assert "2024" in display

    event = model.data(index, Qt.ItemDataRole.UserRole)
    assert isinstance(event, AuditEvent)
    assert event.id == "1"


def test_proxy_filters_by_search_and_category(qt_app: QApplication) -> None:  # noqa: ARG001
    model = AuditEventTableModel(_sample_events())
    proxy = AuditEventFilterProxyModel()
    proxy.setSourceModel(model)

    assert proxy.rowCount() == 2

    proxy.set_search_text("wipe")
    assert proxy.rowCount() == 1

    proxy.set_search_text("")
    proxy.set_category_filter("Configuration")
    assert proxy.rowCount() == 1
    event = proxy.index(0, 0).data(Qt.ItemDataRole.UserRole)
    assert isinstance(event, AuditEvent)
    assert event.category == "Configuration"

    proxy.set_category_filter(None)
    proxy.set_result_filter("Success")
    assert proxy.rowCount() == 1
