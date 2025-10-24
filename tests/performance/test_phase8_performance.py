from __future__ import annotations

import asyncio
import gc
import time
import tracemalloc
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text

from intune_manager.data import (
    AssignmentIntent,
    DeviceRepository,
    ManagedDevice,
    MobileAppRepository,
)
from intune_manager.services.assignments import (
    AssignmentDiff,
    AssignmentService,
    AssignmentUpdate,
)
from tests.factories import (
    bulk_devices,
    bulk_mobile_apps,
    make_mobile_app_assignment,
)
from tests.stubs import FakeGraphClientFactory

pytestmark = pytest.mark.filterwarnings(
    r"ignore:datetime\.datetime\.utcnow\(\) is deprecated:DeprecationWarning"
)


@pytest.mark.usefixtures("qt_app")
def test_device_table_lazy_loading_handles_10k_devices(qtbot):
    """Verify the device table model streams 10K devices without blocking."""

    from intune_manager.ui.devices.models import DeviceTableModel

    model = DeviceTableModel()
    batches: list[int] = []
    model.batch_appended.connect(batches.append)

    start = time.perf_counter()
    model.set_devices_lazy(bulk_devices(10_000), chunk_size=750)

    with qtbot.waitSignal(model.load_finished, timeout=3000):
        pass

    duration = time.perf_counter() - start

    assert model.rowCount() == 10_000
    assert sum(batches) == 10_000
    assert max(batches) <= 750
    assert duration < 2.5, "Lazy loading took longer than expected for 10K devices"


@pytest.mark.asyncio
async def test_cache_memory_profile_large_datasets(database):
    """Ensure repositories cope with large caches without runaway memory usage."""

    repo_devices = DeviceRepository(database)
    repo_apps = MobileAppRepository(database)

    async def device_stream() -> AsyncIterator[ManagedDevice]:
        for device in bulk_devices(10_000):
            yield device
            await asyncio.sleep(0)  # allow Qt event loop integration during bulk load

    tracemalloc.start()
    snapshot_before = tracemalloc.take_snapshot()
    try:
        inserted = await repo_devices.replace_all_async(
            device_stream(),
            tenant_id="tenant-perf",
            chunk_size=512,
        )
        assert inserted == 10_000

        repo_apps.replace_all(
            list(bulk_mobile_apps(5_000)),
            tenant_id="tenant-perf",
        )

        snapshot_after = tracemalloc.take_snapshot()
    finally:
        tracemalloc.stop()

    gc.collect()
    stats = snapshot_after.compare_to(snapshot_before, "filename")
    memory_increase = sum(stat.size_diff for stat in stats if stat.size_diff > 0)

    assert memory_increase < 80 * 1024 * 1024, (
        f"Cache population used too much memory (~{memory_increase / (1024 * 1024):.1f} MiB)"
    )
    assert repo_devices.count(tenant_id="tenant-perf") == 10_000
    assert repo_apps.count(tenant_id="tenant-perf") == 5_000


@pytest.mark.asyncio
async def test_assignment_service_batch_operations_scale():
    """Validate batch application of 10K assignment changes remains efficient."""

    factory = FakeGraphClientFactory()
    factory.set_request_json_response(
        "POST",
        "/deviceAppManagement/mobileApps/app-perf/assign",
        {"status": "ok"},
    )
    service = AssignmentService(factory)

    creates = [
        make_mobile_app_assignment(assignment_id=f"create-{index}").model_copy(
            update={"id": None}
        )
        for index in range(4_000)
    ]
    updates = [
        AssignmentUpdate(
            current=make_mobile_app_assignment(assignment_id=f"existing-{index}"),
            desired=make_mobile_app_assignment(
                assignment_id=f"existing-{index}",
                intent=AssignmentIntent.AVAILABLE,
            ),
        )
        for index in range(3_000)
    ]
    deletes = [
        make_mobile_app_assignment(assignment_id=f"remove-{index}")
        for index in range(3_000)
    ]

    diff = AssignmentDiff(
        to_create=creates,
        to_update=updates,
        to_delete=deletes,
    )

    start = time.perf_counter()
    await service.apply_diff("app-perf", diff)
    duration = time.perf_counter() - start

    assert duration < 2.0, "Batch assignment apply took longer than expected"
    assert len(factory.recorded_requests) == 1
    method, path, payload = factory.recorded_requests[0]
    assert method == "POST"
    assert path == "/deviceAppManagement/mobileApps/app-perf/assign"
    assignments_payload = payload.get("json", {}).get("mobileAppAssignments", [])
    assert len(assignments_payload) == len(creates) + len(updates)
    assert len(factory.executed_batches) == 1
    assert len(factory.executed_batches[0]) == len(deletes)


def test_cache_queries_use_indexes(database):
    """Confirm critical cache lookups leverage SQLite indexes for performance."""

    repo_devices = DeviceRepository(database)
    repo_apps = MobileAppRepository(database)

    repo_devices.replace_all(bulk_devices(10_000), tenant_id="tenant-index")
    repo_apps.replace_all(list(bulk_mobile_apps(5_000)), tenant_id="tenant-index")

    with database.session() as session:
        device_plan = session.exec(
            text(
                "EXPLAIN QUERY PLAN SELECT id FROM devices"
                " WHERE tenant_id = 'tenant-index' AND device_name = 'Device 9999'"
            )
        ).all()
        device_details = " ".join(str(row[-1]) for row in device_plan)
        assert "USING INDEX" in device_details.upper()

        app_plan = session.exec(
            text(
                "EXPLAIN QUERY PLAN SELECT id FROM mobile_apps"
                " WHERE tenant_id = 'tenant-index' AND display_name = 'App app-4999'"
            )
        ).all()
        app_details = " ".join(str(row[-1]) for row in app_plan)
        assert "USING INDEX" in app_details.upper()
