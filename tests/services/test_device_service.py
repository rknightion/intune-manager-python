from __future__ import annotations

from typing import cast

import httpx
import pytest
import respx

from intune_manager.data import DeviceRepository, ManagedDevice
from intune_manager.graph.client import GraphClientConfig, GraphClientFactory
from intune_manager.graph.errors import PermissionError as GraphPermissionError
from intune_manager.graph.requests import DeviceActionName
from intune_manager.services.devices import DeviceActionEvent, DeviceService

from tests.factories import make_access_token, make_managed_device


def _device_payloads(devices: list[ManagedDevice]) -> list[dict[str, object]]:
    return [device.to_graph() for device in devices]


async def _create_service(
    database, *, scopes: list[str] | None = None
) -> tuple[DeviceService, GraphClientFactory]:
    scopes = scopes or ["https://graph.microsoft.com/.default"]
    repository = DeviceRepository(database)
    config = GraphClientConfig(scopes=scopes, enable_telemetry=False)
    factory = GraphClientFactory(lambda _scopes: make_access_token(), config)
    service = DeviceService(factory, repository)
    return service, factory


@pytest.mark.asyncio
@pytest.mark.parametrize("mock_source", ["bespoke", "official"])
async def test_refresh_fetches_and_caches_devices(
    database,
    respx_mock: respx.Router,
    mock_source: str,
    ensure_graph_mock,
) -> None:
    service, factory = await _create_service(database)
    try:
        devices = [
            make_managed_device(device_id="device-1", device_name="Surface"),
            make_managed_device(device_id="device-2", device_name="MacBook"),
        ]
        managed_devices_url = (
            "https://graph.microsoft.com/v1.0/deviceManagement/managedDevices"
        )
        if mock_source == "official":
            ensure_graph_mock("GET", managed_devices_url)
            route = None
        else:
            payload = {"value": _device_payloads(devices)}
            route = respx_mock.get(managed_devices_url).mock(
                return_value=httpx.Response(200, json=payload),
            )

        refreshed_events: list = []
        service.refreshed.subscribe(refreshed_events.append)

        result = await service.refresh()

        if route is not None:
            assert route.called
            assert len(result) == len(devices)
        else:
            assert respx_mock.calls.call_count >= 1
            assert len(result) >= 1
        assert refreshed_events and refreshed_events[0].from_cache is False
        cached = service.list_cached()
        if route is not None:
            assert len(cached) == len(devices)
        else:
            assert len(cached) == len(result)
    finally:
        await factory.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mock_source", ["bespoke", "official"])
async def test_refresh_uses_cache_when_not_stale(
    database,
    respx_mock: respx.Router,
    mock_source: str,
    ensure_graph_mock,
) -> None:
    service, factory = await _create_service(database)
    try:
        devices = [
            make_managed_device(device_id="device-1", device_name="Surface"),
        ]
        managed_devices_url = (
            "https://graph.microsoft.com/v1.0/deviceManagement/managedDevices"
        )
        if mock_source == "official":
            ensure_graph_mock("GET", managed_devices_url)
            route = None
        else:
            payload = {"value": _device_payloads(devices)}
            route = respx_mock.get(managed_devices_url).mock(
                return_value=httpx.Response(200, json=payload),
            )

        await service.refresh()

        if route is not None:
            assert route.call_count == 1
        else:
            assert respx_mock.calls.call_count >= 1
            respx_mock.calls.reset()
        events: list = []
        service.refreshed.subscribe(events.append)
        cached = await service.refresh()

        if route is not None:
            assert route.call_count == 1
        else:
            assert respx_mock.calls.call_count == 0
        assert events and events[0].from_cache is True
        if route is not None:
            assert len(cached) == len(devices)
            assert cached[0].id == devices[0].id
        else:
            assert len(cached) >= 1
    finally:
        await factory.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mock_source", ["bespoke", "official"])
async def test_refresh_emits_error_on_failure(
    database,
    respx_mock: respx.Router,
    mock_source: str,
    ensure_graph_mock,
) -> None:
    service, factory = await _create_service(database)
    try:
        managed_devices_url = (
            "https://graph.microsoft.com/v1.0/deviceManagement/managedDevices"
        )
        if mock_source == "official":
            ensure_graph_mock("GET", managed_devices_url)
            pytest.skip(
                "Official mocks only include successful responses for managedDevices."
            )
        respx_mock.get(managed_devices_url).mock(
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
@pytest.mark.parametrize("mock_source", ["bespoke", "official"])
async def test_refresh_permission_denied_propagates(
    database,
    respx_mock: respx.Router,
    mock_source: str,
    ensure_graph_mock,
) -> None:
    service, factory = await _create_service(database)
    try:
        managed_devices_url = (
            "https://graph.microsoft.com/v1.0/deviceManagement/managedDevices"
        )
        if mock_source == "official":
            ensure_graph_mock("GET", managed_devices_url)
            pytest.skip(
                "Official mocks do not include 403 responses for managedDevices.",
            )

        respx_mock.get(managed_devices_url).mock(
            return_value=httpx.Response(
                403,
                json={"error": {"message": "Forbidden", "code": "Forbidden"}},
            ),
        )

        errors: list = []
        service.errors.subscribe(errors.append)

        with pytest.raises(GraphPermissionError):
            await service.refresh()

        assert errors
        assert isinstance(errors[0].error, GraphPermissionError)
    finally:
        await factory.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mock_source", ["bespoke", "official"])
async def test_perform_action_emits_success_and_failure(
    database,
    respx_mock: respx.Router,
    mock_source: str,
    ensure_graph_mock,
) -> None:
    service, factory = await _create_service(database)
    try:
        sync_url = "https://graph.microsoft.com/v1.0/deviceManagement/managedDevices/device-1/syncDevice"
        wipe_url = "https://graph.microsoft.com/v1.0/deviceManagement/managedDevices/device-2/wipe"
        if mock_source == "official":
            ensure_graph_mock("POST", sync_url)
            success_route = None
        else:
            success_route = respx_mock.post(sync_url).mock(
                return_value=httpx.Response(202, json={}),
            )

        failure_route = respx_mock.post(wipe_url).mock(
            return_value=httpx.Response(500, json={"error": {"message": "nope"}}),
        )

        actions: list[DeviceActionEvent] = []
        service.actions.subscribe(actions.append)
        errors: list = []
        service.errors.subscribe(errors.append)

        await service.perform_action("device-1", cast(DeviceActionName, "syncDevice"))
        if success_route is not None:
            assert success_route.called
        else:
            assert str(respx_mock.calls.last.request.url) == sync_url
            assert respx_mock.calls.last.response.status_code in {200, 202, 204}
        assert actions and actions[-1].success is True

        if mock_source == "official":
            return

        with pytest.raises(Exception):
            await service.perform_action("device-2", cast(DeviceActionName, "wipe"))

        assert failure_route.called
        assert actions[-1].success is False
        assert errors
    finally:
        await factory.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mock_source", ["bespoke", "official"])
async def test_perform_action_permission_denied(
    database,
    respx_mock: respx.Router,
    mock_source: str,
    ensure_graph_mock,
) -> None:
    service, factory = await _create_service(database)
    try:
        sync_url = "https://graph.microsoft.com/v1.0/deviceManagement/managedDevices/device-1/syncDevice"
        if mock_source == "official":
            ensure_graph_mock("POST", sync_url)
            pytest.skip("Official mocks do not include 403 responses for syncDevice.")

        respx_mock.post(sync_url).mock(
            return_value=httpx.Response(
                403,
                json={"error": {"message": "Forbidden", "code": "Forbidden"}},
            ),
        )

        actions: list[DeviceActionEvent] = []
        service.actions.subscribe(actions.append)
        errors: list = []
        service.errors.subscribe(errors.append)

        with pytest.raises(GraphPermissionError):
            await service.perform_action(
                "device-1", cast(DeviceActionName, "syncDevice")
            )

        assert actions
        assert actions[-1].success is False
        assert isinstance(actions[-1].error, GraphPermissionError)
        assert errors
        assert isinstance(errors[0].error, GraphPermissionError)
    finally:
        await factory.close()
