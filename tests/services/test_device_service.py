from __future__ import annotations

from typing import cast

import httpx
import pytest
import respx

from intune_manager.data import DeviceRepository, ManagedDevice
from intune_manager.graph.client import GraphClientConfig, GraphClientFactory
from intune_manager.graph.requests import DeviceActionName
from intune_manager.services.devices import DeviceActionEvent, DeviceService

from tests.factories import make_access_token, make_managed_device


def _device_payloads(devices: list[ManagedDevice]) -> list[dict[str, object]]:
    return [device.to_graph() for device in devices]


async def _create_service(database, *, scopes: list[str] | None = None) -> tuple[DeviceService, GraphClientFactory]:
    scopes = scopes or ["https://graph.microsoft.com/.default"]
    repository = DeviceRepository(database)
    config = GraphClientConfig(scopes=scopes, enable_telemetry=False)
    factory = GraphClientFactory(lambda _scopes: make_access_token(), config)
    service = DeviceService(factory, repository)
    return service, factory


@pytest.mark.asyncio
async def test_refresh_fetches_and_caches_devices(
    database,
    respx_mock: respx.Router,
) -> None:
    service, factory = await _create_service(database)
    try:
        devices = [
            make_managed_device(device_id="device-1", device_name="Surface"),
            make_managed_device(device_id="device-2", device_name="MacBook"),
        ]
        payload = {"value": _device_payloads(devices)}
        route = respx_mock.get(
            "https://graph.microsoft.com/v1.0/deviceManagement/managedDevices",
        ).mock(return_value=httpx.Response(200, json=payload))

        refreshed_events: list = []
        service.refreshed.subscribe(refreshed_events.append)

        result = await service.refresh()

        assert route.called
        assert len(result) == 2
        assert refreshed_events and refreshed_events[0].from_cache is False
        cached = service.list_cached()
        assert len(cached) == 2
    finally:
        await factory.close()


@pytest.mark.asyncio
async def test_refresh_uses_cache_when_not_stale(
    database,
    respx_mock: respx.Router,
) -> None:
    service, factory = await _create_service(database)
    try:
        devices = [
            make_managed_device(device_id="device-1", device_name="Surface"),
        ]
        payload = {"value": _device_payloads(devices)}
    route = respx_mock.get(
        "https://graph.microsoft.com/v1.0/deviceManagement/managedDevices",
    ).mock(return_value=httpx.Response(200, json=payload))

    await service.refresh()

    assert route.call_count == 1
    events: list = []
    service.refreshed.subscribe(events.append)
    cached = await service.refresh()

    assert route.call_count == 1
    assert events and events[0].from_cache is True
    assert len(cached) == 1
    assert cached[0].id == devices[0].id
    finally:
        await factory.close()


@pytest.mark.asyncio
async def test_refresh_emits_error_on_failure(
    database,
    respx_mock: respx.Router,
) -> None:
    service, factory = await _create_service(database)
    try:
        respx_mock.get(
            "https://graph.microsoft.com/v1.0/deviceManagement/managedDevices",
        ).mock(
            return_value=httpx.Response(
                500,
                json={"error": {"message": "Internal error"}},
            ),
        )

        errors: list = []
        service.errors.subscribe(errors.append)

        with pytest.raises(Exception):
            await service.refresh()

        assert errors
        assert isinstance(errors[0].error, Exception)
    finally:
        await factory.close()


@pytest.mark.asyncio
async def test_perform_action_emits_success_and_failure(
    database,
    respx_mock: respx.Router,
) -> None:
    service, factory = await _create_service(database)
    try:
        success_route = respx_mock.post(
            "https://graph.microsoft.com/v1.0/deviceManagement/managedDevices/device-1/syncDevice",
        ).mock(return_value=httpx.Response(202, json={}))

        failure_route = respx_mock.post(
            "https://graph.microsoft.com/v1.0/deviceManagement/managedDevices/device-2/wipe",
        ).mock(return_value=httpx.Response(500, json={"error": {"message": "nope"}}))

        actions: list[DeviceActionEvent] = []
        service.actions.subscribe(actions.append)
        errors: list = []
        service.errors.subscribe(errors.append)

        await service.perform_action("device-1", cast(DeviceActionName, "syncDevice"))
        assert success_route.called
        assert actions and actions[-1].success is True

        with pytest.raises(Exception):
            await service.perform_action("device-2", cast(DeviceActionName, "wipe"))

        assert failure_route.called
        assert actions[-1].success is False
        assert errors
    finally:
        await factory.close()
