from __future__ import annotations

import pytest

from intune_manager.services.sync import SyncProgressEvent, SyncService


@pytest.mark.asyncio
async def test_sync_service_emits_progress_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    phases = ["devices", "applications", "groups", "filters", "configurations", "audit"]
    sync = SyncService(
        devices="devices",
        applications="applications",
        groups="groups",
        filters="filters",
        configurations="configurations",
        audit="audit",
    )

    invoked: list[str] = []

    async def fake_refresh(service, **kwargs):
        invoked.append(service)

    monkeypatch.setattr(sync, "_refresh_single", fake_refresh)

    events: list[SyncProgressEvent] = []
    sync.progress.subscribe(events.append)

    await sync.refresh_all()

    assert invoked == phases
    assert [event.phase for event in events] == phases
    assert [event.completed for event in events] == list(range(1, len(phases) + 1))
    assert all(event.total == len(phases) for event in events)


@pytest.mark.asyncio
async def test_sync_service_emits_error_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync = SyncService(
        devices="devices",
        applications="applications",
        groups="groups",
        filters="filters",
        configurations="configurations",
        audit="audit",
    )

    async def fake_refresh(service, **kwargs):
        if service == "groups":
            raise RuntimeError("group refresh failed")

    monkeypatch.setattr(sync, "_refresh_single", fake_refresh)

    errors = []
    sync.errors.subscribe(errors.append)

    with pytest.raises(RuntimeError, match="group refresh failed"):
        await sync.refresh_all(tenant_id="tenant")

    assert errors
    assert errors[0].tenant_id == "tenant"
    assert isinstance(errors[0].error, RuntimeError)
