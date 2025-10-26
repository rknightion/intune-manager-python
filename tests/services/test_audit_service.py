from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from intune_manager.data import AuditEventRepository
from intune_manager.graph.client import GraphClientConfig, GraphClientFactory
from intune_manager.graph.errors import RateLimitError
from intune_manager.services import AuditLogService

from tests.factories import make_access_token


async def _create_audit_service(
    database, *, scopes: list[str] | None = None
) -> tuple[AuditLogService, GraphClientFactory]:
    repository = AuditEventRepository(database)
    config = GraphClientConfig(
        scopes=scopes or ["https://graph.microsoft.com/.default"],
        enable_telemetry=False,
    )
    factory = GraphClientFactory(lambda _: make_access_token(), config)
    service = AuditLogService(factory, repository)
    return service, factory


@pytest.mark.asyncio
async def test_refresh_includes_order_and_time_window_filter(
    database,
    respx_mock: respx.Router,
) -> None:
    service, factory = await _create_audit_service(database)
    try:
        captured_urls: list[str] = []

        def _responder(request: httpx.Request) -> httpx.Response:
            captured_urls.append(str(request.url))
            return httpx.Response(200, json={"value": []})

        respx_mock.get(
            re.compile(r"https://graph\.microsoft\.com/beta/deviceManagement/auditEvents.*")
        ).mock(side_effect=_responder)

        await service.refresh()

        assert captured_urls, "Expected at least one audit request"
        first_url = captured_urls[0]
        parsed = urlparse(first_url)
        query = parse_qs(parsed.query)
        assert query.get("$orderby") == ["activityDateTime desc"]
        assert query.get("$top") == ["100"]
        assert "$filter" in query
        assert query["$filter"][0].startswith("activityDateTime ge ")
    finally:
        await factory.close()


@pytest.mark.asyncio
async def test_refresh_persists_partial_results_when_rate_limited(
    database,
    respx_mock: respx.Router,
) -> None:
    service, factory = await _create_audit_service(database)
    try:
        first_page = {
            "value": [
                {
                    "id": "audit-1",
                    "displayName": "Updated device",
                    "activityDateTime": "2025-10-20T10:00:00Z",
                }
            ],
            "@odata.nextLink": "https://graph.microsoft.com/beta/deviceManagement/auditEvents?$skiptoken=token",
        }

        responses = [
            httpx.Response(200, json=first_page),
            httpx.Response(
                429,
                json={"error": {"message": "Too many requests"}},
                headers={"Retry-After": "1"},
            ),
        ]

        call_tracker = {"count": 0}

        def _side_effect(request: httpx.Request) -> httpx.Response:
            index = min(call_tracker["count"], len(responses) - 1)
            call_tracker["count"] += 1
            return responses[index]

        respx_mock.get(
            re.compile(r"https://graph\.microsoft\.com/beta/deviceManagement/auditEvents.*")
        ).mock(side_effect=_side_effect)

        events = await service.refresh()
        assert len(events) == 1
        cached = service.list_cached()
        assert len(cached) == 1
    finally:
        await factory.close()


@pytest.mark.asyncio
async def test_refresh_raises_when_rate_limited_without_results(
    database,
    respx_mock: respx.Router,
) -> None:
    service, factory = await _create_audit_service(database)
    try:
        respx_mock.get(
            re.compile(r"https://graph\.microsoft\.com/beta/deviceManagement/auditEvents.*")
        ).mock(
            return_value=httpx.Response(
                429,
                json={"error": {"message": "Too many requests"}},
                headers={"Retry-After": "2"},
            )
        )

        with pytest.raises(RateLimitError):
            await service.refresh()
    finally:
        await factory.close()
