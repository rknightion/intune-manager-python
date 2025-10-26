from __future__ import annotations

import pytest

from intune_manager.services import (
    ApplicationService,
    AssignmentFilterService,
    AuditLogService,
    ConfigurationService,
    DeviceService,
    GroupService,
    ServiceErrorEvent,
    SyncService,
)


class _StubService:
    def __init__(self, *, fail: bool = False, name: str = "") -> None:
        self.fail = fail
        self.name = name or type(self).__name__
        self.calls = 0

    async def refresh(self, *_, **__) -> list[object]:
        self.calls += 1
        if self.fail:
            raise RuntimeError(f"{self.name} failed")
        return []


class StubDeviceService(_StubService, DeviceService):
    def __init__(self, *, fail: bool = False) -> None:
        super().__init__(fail=fail, name="devices")


class StubApplicationService(_StubService, ApplicationService):
    def __init__(self, *, fail: bool = False) -> None:
        super().__init__(fail=fail, name="applications")


class StubGroupService(_StubService, GroupService):
    def __init__(self, *, fail: bool = False) -> None:
        super().__init__(fail=fail, name="groups")


class StubAssignmentFilterService(_StubService, AssignmentFilterService):
    def __init__(self, *, fail: bool = False) -> None:
        super().__init__(fail=fail, name="assignment filters")


class StubConfigurationService(_StubService, ConfigurationService):
    def __init__(self, *, fail: bool = False) -> None:
        super().__init__(fail=fail, name="configurations")


class StubAuditLogService(_StubService, AuditLogService):
    def __init__(self, *, fail: bool = False) -> None:
        super().__init__(fail=fail, name="audit")


@pytest.mark.asyncio
async def test_sync_service_continues_after_phase_failure() -> None:
    device = StubDeviceService(fail=True)
    applications = StubApplicationService()
    groups = StubGroupService()
    filters = StubAssignmentFilterService()
    configurations = StubConfigurationService()
    audit = StubAuditLogService()

    sync = SyncService(
        devices=device,
        applications=applications,
        groups=groups,
        filters=filters,
        configurations=configurations,
        audit=audit,
    )

    errors: list[ServiceErrorEvent] = []
    progresses: list[object] = []
    sync.errors.subscribe(lambda event: errors.append(event))
    sync.progress.subscribe(lambda event: progresses.append(event))

    await sync.refresh_all(force=True)

    assert device.calls == 1
    assert applications.calls == 1
    assert groups.calls == 1
    assert len(errors) == 1
    assert progresses
    final_progress = progresses[-1]
    assert final_progress.completed == final_progress.total == 6
