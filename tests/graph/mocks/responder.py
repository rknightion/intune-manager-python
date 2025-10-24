from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import httpx
import respx

from .repository import GraphMock, GraphMockRepository, load_default_repository


@dataclass(slots=True)
class GraphMockResponder:
    """Callable that serves Graph responses backed by the mock repository."""

    repository: GraphMockRepository
    strict: bool = True
    recorded: list[tuple[str, str]] | None = None

    def __post_init__(self) -> None:
        if self.recorded is None:
            self.recorded = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        method = request.method.upper()
        match = self.repository.match(method, url)
        if match is None:
            self.recorded.append((method, url))
            if self.strict:
                raise AssertionError(
                    f"No Graph mock found for {method} {url}. "
                    "Add the endpoint to the test dataset or allow fallbacks.",
                )
            return httpx.Response(
                status_code=404,
                json={"error": f"No mock available for {method} {url}"},
                request=request,
            )
        return _build_response(match, request=request)

    def assert_all_matched(self) -> None:
        if self.recorded:
            formatted = "\n".join(f"- {method} {url}" for method, url in self.recorded)
            raise AssertionError(
                f"Unmocked Graph requests encountered:\n{formatted}",
            )


def register_graph_mocks(
    router: respx.Router,
    repository: GraphMockRepository | None = None,
    *,
    strict: bool = True,
    methods: Iterable[str] | None = None,
) -> GraphMockResponder:
    """Register a catch-all responder for Graph endpoints on the router."""

    repo = repository or load_default_repository()
    responder = GraphMockResponder(repository=repo, strict=strict)
    method_list = tuple(methods) if methods is not None else repo.methods
    if not method_list:
        method_list = ("GET", "POST", "PATCH", "PUT", "DELETE")

    for method in method_list:
        router.route(
            method=method,
            host="graph.microsoft.com",
        ).mock(side_effect=responder)

    return responder


def _build_response(match: GraphMock, *, request: httpx.Request) -> httpx.Response:
    headers = dict(match.response_headers)
    body = match.response_body
    if isinstance(body, (dict, list)):
        return httpx.Response(
            status_code=match.response_status,
            json=body,
            headers=headers,
            request=request,
        )
    if isinstance(body, str):
        return httpx.Response(
            status_code=match.response_status,
            text=body,
            headers=headers,
            request=request,
        )
    return httpx.Response(
        status_code=match.response_status,
        headers=headers,
        request=request,
    )
