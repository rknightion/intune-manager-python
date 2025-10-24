from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal, Sequence
from urllib.parse import urlencode


GraphMethod = Literal["GET", "POST", "PATCH", "DELETE", "PUT"]
BETA_VERSION = "beta"


@dataclass(slots=True)
class GraphRequest:
    """Structured representation of a Microsoft Graph request."""

    method: GraphMethod
    url: str
    request_id: str | None = None
    headers: dict[str, str] | None = None
    body: Any | None = None
    params: dict[str, Any] | None = None
    api_version: str | None = None
    depends_on: Sequence[str] | None = None


@dataclass(slots=True)
class GraphBatch:
    requests: list[dict[str, Any]]


def build_batch_requests(requests: Iterable[GraphRequest]) -> list[dict[str, Any]]:
    batch: list[dict[str, Any]] = []
    for index, request in enumerate(requests, start=1):
        batch.append(
            graph_request_to_batch_entry(request, request_id=str(index)),
        )
    return batch


DeviceActionName = Literal[
    "syncDevice",
    "retire",
    "wipe",
    "rebootNow",
    "shutDown",
]


def device_action_request(
    device_id: str,
    action: DeviceActionName,
    *,
    body: dict[str, Any] | None = None,
) -> GraphRequest:
    """Construct a POST request targeting managed device operations."""

    path = f"/deviceManagement/managedDevices/{device_id}/{action}"
    payload = body or {}
    return GraphRequest(
        method="POST",
        url=path,
        body=payload,
    )


def mobile_app_assign_request(
    app_id: str,
    assignments: Sequence[dict[str, Any]],
) -> GraphRequest:
    """Builds the mobile app assign endpoint request."""

    path = f"/deviceAppManagement/mobileApps/{app_id}/assign"
    return GraphRequest(
        method="POST",
        url=path,
        body={"mobileAppAssignments": list(assignments)},
        api_version=BETA_VERSION,
    )


def mobile_app_assignments_request(
    app_id: str,
    *,
    params: dict[str, Any] | None = None,
) -> GraphRequest:
    """Fetch the assignments collection for a given mobile app."""

    path = f"/deviceAppManagement/mobileApps/{app_id}/assignments"
    return GraphRequest(
        method="GET",
        url=path,
        params=params,
    )


def mobile_app_assignment_update_request(
    app_id: str,
    assignment_id: str,
    payload: dict[str, Any],
) -> GraphRequest:
    path = f"/deviceAppManagement/mobileApps/{app_id}/assignments/{assignment_id}"
    return GraphRequest(method="PATCH", url=path, body=payload)


def mobile_app_assignment_delete_request(
    app_id: str, assignment_id: str
) -> GraphRequest:
    path = f"/deviceAppManagement/mobileApps/{app_id}/assignments/{assignment_id}"
    return GraphRequest(method="DELETE", url=path)


def mobile_app_install_summary_request(app_id: str) -> GraphRequest:
    path = f"/deviceAppManagement/mobileApps/{app_id}/installSummary"
    return GraphRequest(method="GET", url=path, api_version=BETA_VERSION)


def mobile_app_icon_request(
    app_id: str,
    size: Literal["large", "small"] = "large",
) -> GraphRequest:
    """Generate a binary icon download request for a managed mobile app."""

    suffix = "largeIcon" if size == "large" else "smallIcon"
    path = f"/deviceAppManagement/mobileApps/{app_id}/{suffix}/$value"
    return GraphRequest(
        method="GET",
        url=path,
        headers={"Accept": "image/png"},
        api_version=BETA_VERSION,
    )


def configuration_assign_request(
    configuration_id: str,
    body: dict[str, Any],
    *,
    endpoint: Literal[
        "deviceConfigurations", "configurationPolicies"
    ] = "deviceConfigurations",
) -> GraphRequest:
    """Build assign request for configuration profiles and templates."""

    path = f"/deviceManagement/{endpoint}/{configuration_id}/assign"
    api_version = BETA_VERSION if endpoint == "configurationPolicies" else None
    return GraphRequest(method="POST", url=path, body=body, api_version=api_version)


def audit_events_request(
    *,
    params: dict[str, Any] | None = None,
) -> GraphRequest:
    path = "/deviceManagement/auditEvents"
    return GraphRequest(
        method="GET",
        url=path,
        params=params,
        headers={"ConsistencyLevel": "eventual"},
        api_version=BETA_VERSION,
    )


def assignment_filters_request(
    *,
    params: dict[str, Any] | None = None,
) -> GraphRequest:
    path = "/deviceManagement/assignmentFilters"
    return GraphRequest(method="GET", url=path, params=params, api_version=BETA_VERSION)


def graph_request_to_batch_entry(
    request: GraphRequest,
    *,
    request_id: str,
) -> dict[str, Any]:
    effective_id = request.request_id or request_id
    url = _normalise_batch_url(request.url, request.api_version, request.params)
    entry: dict[str, Any] = {
        "id": effective_id,
        "method": request.method,
        "url": url,
    }
    if request.headers:
        entry["headers"] = request.headers
    if request.body is not None and request.method in {"POST", "PATCH", "PUT"}:
        entry["body"] = request.body
    if request.depends_on:
        entry["dependsOn"] = list(request.depends_on)
    return entry


def _normalise_batch_url(
    url: str,
    api_version: str | None,
    params: dict[str, Any] | None,
) -> str:
    if not url.startswith("/"):
        url = "/" + url
    if api_version:
        if not url.startswith(f"/{api_version}"):
            url = f"/{api_version}{url}"
    if params:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{urlencode(params, doseq=True)}"
    return url


__all__ = [
    "GraphRequest",
    "GraphBatch",
    "GraphMethod",
    "build_batch_requests",
    "graph_request_to_batch_entry",
    "device_action_request",
    "mobile_app_assign_request",
    "mobile_app_assignments_request",
    "mobile_app_assignment_update_request",
    "mobile_app_assignment_delete_request",
    "mobile_app_install_summary_request",
    "mobile_app_icon_request",
    "configuration_assign_request",
    "audit_events_request",
    "assignment_filters_request",
    "DeviceActionName",
]
