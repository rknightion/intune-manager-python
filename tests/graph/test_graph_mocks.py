from __future__ import annotations

import httpx
import pytest


def test_repository_matches_known_endpoint(graph_mock_repository) -> None:
    example = graph_mock_repository.find_by_prefix(
        "GET",
        "https://graph.microsoft.com/beta/deviceManagement/virtualEndpoint/provisioningPolicies/",
    )[0]
    assert example.example_url is not None
    matched = graph_mock_repository.match("GET", example.example_url)
    assert matched is not None
    assert matched.response_status == 200
    assert matched.version == "beta"


@pytest.mark.asyncio
async def test_graph_mock_respx_serves_responses(
    graph_mock_respx,
    graph_mock_repository,
) -> None:
    sample = next(
        entry
        for entry in graph_mock_repository.iter("GET")
        if entry.example_url is not None
    )

    async with httpx.AsyncClient() as client:
        response = await client.get(sample.example_url)

    assert response.status_code == sample.response_status
    payload = response.json()
    assert isinstance(payload, dict)
