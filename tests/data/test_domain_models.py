from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from intune_manager.data import (
    AuditEvent,
    AllDevicesAssignmentTarget,
    AssignmentFilter,
    AssignmentFilterPlatform,
    AssignmentIntent,
    AssignmentSettings,
    ConfigurationPlatform,
    ConfigurationProfile,
    DirectoryGroup,
    ManagedDevice,
    MobileApp,
    MobileAppAssignment,
    MobileAppPlatform,
)
from intune_manager.data.validation import GraphResponseValidator


def test_managed_device_round_trip_serialization() -> None:
    payload = {
        "id": "device-123",
        "deviceName": "Surface Pro",
        "operatingSystem": "Windows",
        "lastSyncDateTime": "2024-01-01T12:00:00Z",
    }
    device = ManagedDevice.from_graph(payload)

    assert device.device_name == "Surface Pro"
    assert device.last_sync_date_time is not None

    serialized = device.to_graph()
    assert serialized["deviceName"] == "Surface Pro"
    assert serialized["operatingSystem"] == "Windows"
    assert "lastSyncDateTime" in serialized


def test_assignment_models_include_graph_aliases() -> None:
    target = AllDevicesAssignmentTarget()
    settings = AssignmentSettings(start_date_time=datetime(2024, 1, 1, 9, 0, 0))
    assignment = MobileAppAssignment(
        id="assignment-1",
        intent=AssignmentIntent.REQUIRED,
        target=target,
        settings=settings,
    )

    payload = assignment.to_graph()
    assert payload["target"]["@odata.type"] == target.odata_type
    assert payload["intent"] == "required"
    assert "startDateTime" in payload["settings"]


def test_model_validation_errors_surface_fields() -> None:
    payload = {"id": "broken-device"}
    with pytest.raises(ValidationError):
        ManagedDevice.from_graph(payload)


def test_graph_response_validator_collects_issues() -> None:
    validator = GraphResponseValidator("devices")

    valid = validator.parse(
        ManagedDevice,
        {
            "id": "device-1",
            "deviceName": "Surface",
            "operatingSystem": "Windows",
        },
    )
    assert valid is not None

    invalid = validator.parse(
        ManagedDevice,
        {
            "id": "device-2",
            "operatingSystem": "Windows",
        },
    )
    assert invalid is None
    issues = validator.issues()
    assert len(issues) == 1
    assert "deviceName" in issues[0].fields[0]


def test_assignment_filter_platform_accepts_graph_casing() -> None:
    payload = {
        "id": "filter-1",
        "displayName": "iOS filter",
        "platform": "iOS",
    }
    assignment_filter = AssignmentFilter.from_graph(payload)

    assert assignment_filter.platform == AssignmentFilterPlatform.IOS


def test_configuration_profile_accepts_name_and_platforms_aliases() -> None:
    payload = {
        "id": "config-1",
        "name": "Policy Name",
        "platforms": "iOS",
        "technologies": "mdm",
    }
    profile = ConfigurationProfile.from_graph(payload)

    assert profile.display_name == "Policy Name"
    assert profile.platform_type == ConfigurationPlatform.IOS


def test_mobile_app_platform_accepts_graph_casing() -> None:
    payload = {
        "id": "app-1",
        "name": "App",
        "platformType": "iOS",
    }
    app = MobileApp.from_graph(payload)

    assert app.display_name == "App"
    assert app.platform_type == MobileAppPlatform.IOS


def test_mobile_app_infers_pkg_from_filename() -> None:
    payload = {
        "id": "app-2",
        "displayName": "macOS PKG",
        "fileName": "example.pkg",
    }

    app = MobileApp.from_graph(payload)

    assert app.platform_type == MobileAppPlatform.MACOS
    assert app.app_type == "PKG"


def test_mobile_app_infers_windows_type_from_filename() -> None:
    payload = {
        "id": "app-3",
        "displayName": "Installer",
        "fileName": "installer.msi",
    }

    app = MobileApp.from_graph(payload)

    assert app.platform_type == MobileAppPlatform.WINDOWS
    assert app.app_type == "MSI"


def test_mobile_app_infers_platform_for_winget_app() -> None:
    payload = {
        "id": "app-4",
        "displayName": "Winget App",
        "@odata.type": "#microsoft.graph.winGetApp",
    }

    app = MobileApp.from_graph(payload)

    assert app.platform_type == MobileAppPlatform.WINDOWS
    assert app.app_type == "WinGet"


def test_directory_group_accepts_name_alias() -> None:
    payload = {
        "id": "group-1",
        "name": "Ops",
    }
    group = DirectoryGroup.from_graph(payload)

    assert group.display_name == "Ops"


def test_audit_event_accepts_name_alias() -> None:
    payload = {
        "id": "audit-1",
        "name": "Operation",
    }
    event = AuditEvent.from_graph(payload)

    assert event.display_name == "Operation"
