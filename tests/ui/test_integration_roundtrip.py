from __future__ import annotations

import httpx
import pytest
import respx

from intune_manager.data import DeviceRepository
from intune_manager.graph.client import GraphClientConfig, GraphClientFactory
from intune_manager.services.devices import DeviceService
from intune_manager.services.registry import ServiceRegistry
from intune_manager.ui.devices.controller import DeviceController
from intune_manager.ui.devices.models import DeviceTableModel

from tests.factories import configure_auth_manager, make_managed_device, make_settings
from tests.stubs import StubPublicClientApplication


@pytest.mark.parametrize("mock_source", ["bespoke", "official"])
@pytest.mark.asyncio
async def test_auth_graph_service_repository_round_trip(
    qt_app,  # noqa: ARG001 - ensures Qt environment
    database,
    monkeypatch: pytest.MonkeyPatch,
    respx_mock: respx.Router,
    ensure_graph_mock,
    mock_source: str,
) -> None:
    settings = make_settings()
    stub = StubPublicClientApplication(
        client_id="",
        authority="",
        accounts=[],
        interactive_results=[
            {
                "access_token": "header.payload.signature",
                "expires_in": 3600,
                "id_token_claims": {
                    "name": "UITester",
                    "preferred_username": "uitester@contoso.com",
                    "oid": "oid-0001",
                    "tid": "tenant-0001",
                },
            }
        ],
    )

    manager = configure_auth_manager(
        settings=settings,
        stub_app=stub,
        monkeypatch=monkeypatch,
    )

    token = await manager.acquire_token(["https://graph.microsoft.com/.default"])
    assert token.token

    devices = [
        make_managed_device(device_id="device-1", device_name="Surface Pro 9"),
        make_managed_device(device_id="device-2", device_name="MacBook Pro"),
    ]

    factory = GraphClientFactory(
        manager.token_provider(),
        GraphClientConfig(
            scopes=["https://graph.microsoft.com/.default"], enable_telemetry=False
        ),
    )
    try:
        managed_devices_url = (
            "https://graph.microsoft.com/v1.0/deviceManagement/managedDevices"
        )
        if mock_source == "official":
            ensure_graph_mock("GET", managed_devices_url)
        else:
            respx_mock.get(managed_devices_url).mock(
                return_value=httpx.Response(
                    200,
                    json={"value": [d.to_graph() for d in devices]},
                ),
            )

        repository = DeviceRepository(database)
        service = DeviceService(factory, repository)
        controller = DeviceController(ServiceRegistry(devices=service))

        refreshed_events: list[tuple[list, bool]] = []
        controller.register_callbacks(
            refreshed=lambda items, from_cache: refreshed_events.append(
                (list(items), from_cache)
            ),
        )

        result = await controller.refresh()

        if mock_source == "bespoke":
            assert len(result) == len(devices)
        else:
            assert respx_mock.calls.call_count >= 1
            assert isinstance(result, list)
        assert refreshed_events and refreshed_events[0][1] is False

        model = DeviceTableModel()
        model.set_devices(result)
        assert model.rowCount() == len(result)
        if result:
            first_device = model.data(model.index(0, 0))
            assert isinstance(first_device, str)

        cached = controller.list_cached()
        assert len(cached) == len(result)
        assert not controller.is_cache_stale()
    finally:
        await factory.close()
