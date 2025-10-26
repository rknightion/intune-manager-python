from __future__ import annotations

from intune_manager.data.cache_health import CacheIntegrityChecker
from intune_manager.data.repositories.base import DEFAULT_SCOPE
from intune_manager.data.sql import CacheEntry, DeviceRecord


def test_cache_integrity_handles_scalar_entries(database) -> None:
    checker = CacheIntegrityChecker(database)
    with database.session() as session:
        session.add(
            CacheEntry(
                resource="devices",
                scope=DEFAULT_SCOPE,
                tenant_id=None,
                item_count=0,
            ),
        )
        session.commit()

    report = checker.inspect(auto_repair=False)

    assert any(entry.resource == "devices" for entry in report.entries)


def test_cache_integrity_handles_tenant_rows(database) -> None:
    checker = CacheIntegrityChecker(database)
    with database.session() as session:
        session.add(
            DeviceRecord(
                id="device-tenant",
                tenant_id="tenant-123",
                device_name="Surface",
                operating_system="Windows",
                payload={
                    "deviceName": "Surface",
                    "operatingSystem": "Windows",
                },
            ),
        )
        session.commit()

    report = checker.inspect(auto_repair=False)

    assert any(
        entry.resource == "devices" and entry.scope == "tenant-123"
        for entry in report.entries
    )
