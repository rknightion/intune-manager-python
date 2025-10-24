from __future__ import annotations

from datetime import datetime, timedelta
from typing import AsyncIterator

import pytest

from intune_manager.data import DeviceRepository, ManagedDevice

from tests.factories import make_managed_device


def test_replace_all_updates_cache_metadata(database) -> None:
    repository = DeviceRepository(database)
    devices = [
        make_managed_device(device_id="device-1", device_name="Surface"),
        make_managed_device(device_id="device-2", device_name="MacBook"),
    ]

    repository.replace_all(devices, tenant_id="tenant", expires_in=timedelta(minutes=5))

    stored = repository.list_all(tenant_id="tenant")
    assert len(stored) == 2
    assert repository.count(tenant_id="tenant") == 2
    assert repository.cached_count(tenant_id="tenant") == 2
    assert repository.is_cache_stale(tenant_id="tenant") is False
    entry = repository.cache_entry(tenant_id="tenant")
    assert entry is not None
    assert entry.item_count == 2


def test_cache_expiry_detection(database, monkeypatch: pytest.MonkeyPatch) -> None:
    repository = DeviceRepository(database)
    devices = [make_managed_device(device_id="device-1")]
    initial = datetime(2024, 1, 1, 12, 0, 0)

    monkeypatch.setattr(
        "intune_manager.data.repositories.base._utc_now",
        lambda: initial,
    )
    repository.replace_all(devices, expires_in=timedelta(seconds=10))
    assert repository.is_cache_stale() is False

    later = initial + timedelta(seconds=11)
    monkeypatch.setattr(
        "intune_manager.data.repositories.base._utc_now",
        lambda: later,
    )
    assert repository.is_cache_stale() is True


def test_clear_removes_records_and_cache(database) -> None:
    repository = DeviceRepository(database)
    repository.replace_all([make_managed_device(device_id="device-1")])
    assert repository.list_all()

    repository.clear()
    assert repository.list_all() == []
    assert repository.cache_entry() is None


@pytest.mark.asyncio
async def test_replace_all_async_streams_without_materialising(database) -> None:
    repository = DeviceRepository(database)

    async def device_stream() -> AsyncIterator[ManagedDevice]:
        for index in range(5):
            yield make_managed_device(device_id=f"device-{index}")

    count = await repository.replace_all_async(
        device_stream(),
        chunk_size=2,
        expires_in=timedelta(minutes=1),
    )

    assert count == 5
    assert repository.count() == 5
    assert len(repository.list_all()) == 5
