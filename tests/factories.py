from __future__ import annotations

import time
from datetime import datetime
from typing import Iterable

from intune_manager.auth.types import AccessToken
from intune_manager.config.settings import Settings
from intune_manager.data import (
    AllDevicesAssignmentTarget,
    AssignmentIntent,
    AssignmentSettings,
    ManagedDevice,
    MobileAppAssignment,
)


def make_access_token(token: str = "token", expires_in: int = 3600) -> AccessToken:
    """Return a short-lived access token suitable for Graph client tests."""

    return AccessToken(token=token, expires_on=int(time.time()) + expires_in)


def make_settings(**overrides: object) -> Settings:
    """Build Settings populated with safe defaults for auth scenarios."""

    settings = Settings(
        tenant_id="contoso.onmicrosoft.com",
        client_id="00000000-0000-0000-0000-000000000000",
        redirect_uri="http://localhost/auth",
    )
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


def make_managed_device(
    *,
    device_id: str,
    device_name: str | None = None,
    operating_system: str = "Windows",
    last_sync: datetime | None = None,
    **overrides: object,
) -> ManagedDevice:
    """Create a ManagedDevice instance using Graph aliases."""

    payload: dict[str, object] = {
        "id": device_id,
        "deviceName": device_name or f"Device-{device_id}",
        "operatingSystem": operating_system,
        "userPrincipalName": f"user.{device_id}@contoso.com",
    }
    if last_sync is not None:
        payload["lastSyncDateTime"] = last_sync.isoformat()
    payload.update(overrides)
    return ManagedDevice.from_graph(payload)


def make_mobile_app_assignment(
    *,
    assignment_id: str,
    intent: AssignmentIntent = AssignmentIntent.REQUIRED,
    target: AllDevicesAssignmentTarget | None = None,
    settings: AssignmentSettings | None = None,
) -> MobileAppAssignment:
    """Construct an immutable MobileAppAssignment for diffing scenarios."""

    target_model = target or AllDevicesAssignmentTarget()
    settings_model = settings or AssignmentSettings()
    return MobileAppAssignment(
        id=assignment_id,
        intent=intent,
        target=target_model,
        settings=settings_model,
    )


def clone_assignment_with_updates(
    assignment: MobileAppAssignment,
    *,
    new_intent: AssignmentIntent | None = None,
    settings_overrides: dict[str, object] | None = None,
) -> MobileAppAssignment:
    """Return a copy of an assignment with updated intent/settings."""

    settings_model = assignment.settings or AssignmentSettings()
    if settings_overrides:
        settings_model = AssignmentSettings.model_validate(
            {
                **settings_model.model_dump(),
                **settings_overrides,
            }
        )
    return MobileAppAssignment(
        id=assignment.id,
        intent=new_intent or assignment.intent,
        target=assignment.target,
        settings=settings_model,
    )


def bulk_devices(count: int) -> Iterable[ManagedDevice]:
    """Generate a collection of ManagedDevice instances for load testing."""

    for index in range(count):
        yield make_managed_device(
            device_id=f"device-{index}",
            device_name=f"Device {index}",
            operating_system="Windows",
        )
