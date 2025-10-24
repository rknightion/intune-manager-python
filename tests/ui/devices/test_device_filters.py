from __future__ import annotations

import pytest

from intune_manager.data.models.device import ComplianceState, Ownership
from intune_manager.ui.devices.models import DeviceFilterProxyModel, DeviceTableModel

from tests.factories import make_managed_device


@pytest.mark.usefixtures("qt_app")
def test_devices_widget_filters_search_and_platform():
    def _normalize(device):
        updates = {}
        if isinstance(device.compliance_state, str):
            updates["compliance_state"] = ComplianceState(device.compliance_state)
        if isinstance(device.ownership, str):
            updates["ownership"] = Ownership(device.ownership)
        return device.model_copy(update=updates) if updates else device

    devices = [
        _normalize(
            make_managed_device(
                device_id="device-1",
                device_name="Surface Pro 9",
                operating_system="Windows",
                complianceState="compliant",
                ownership="company",
                enrollmentType="companyPortal",
            )
        ),
        _normalize(
            make_managed_device(
                device_id="device-2",
                device_name="iPhone 14",
                operating_system="iOS",
                complianceState="noncompliant",
                ownership="personal",
                enrollmentType="appleConfigurator",
            )
        ),
        _normalize(
            make_managed_device(
                device_id="device-3",
                device_name="MacBook Air",
                operating_system="macOS",
                complianceState="compliant",
                ownership="company",
                enrollmentType="companyPortal",
            )
        ),
    ]

    model = DeviceTableModel(devices)
    proxy = DeviceFilterProxyModel()
    proxy.setSourceModel(model)

    assert proxy.rowCount() == 3

    proxy.set_search_text("surface")
    assert proxy.rowCount() == 1

    proxy.set_search_text("")
    assert proxy.rowCount() == 3

    proxy.set_platform_filter("iOS")
    assert proxy.rowCount() == 1

    proxy.set_platform_filter(None)
    assert proxy.rowCount() == 3

    proxy.set_search_text("Surface'; DROP TABLE devices;--")
    assert proxy._search_text == "surface drop table devices--"
