from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from intune_manager.data import (
    AllDevicesAssignmentTarget,
    AssignmentIntent,
    AssignmentSettings,
    ManagedDevice,
    MobileAppAssignment,
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
