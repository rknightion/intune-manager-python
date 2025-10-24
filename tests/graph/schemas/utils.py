from __future__ import annotations

import re
from typing import Iterable


INTUNE_PREFIXES: tuple[str, ...] = (
    "deviceManagement",
    "deviceAppManagement",
    "deviceManagementScripts",
    "deviceManagementIntent",
    "deviceManagementPartners",
    "deviceManagementReports",
    "deviceManagementExchangeConnector",
    "deviceManagementCompliancePolicies",
)

_PATH_PARAM_PATTERN = re.compile(r"\{[^}]+\}")
_AT_PARAM_PATTERN = re.compile(r"=@[^,)]+")


def normalise_openapi_path(path: str) -> str:
    path_without_version = path.lstrip("/")
    substituted = _PATH_PARAM_PATTERN.sub("*", path_without_version)
    substituted = _AT_PARAM_PATTERN.sub("=*", substituted)
    substituted = substituted.replace("'", "")
    substituted = substituted.replace(" ", "")
    substituted = substituted.replace("microsoft.graph.", "graph.")
    return substituted.rstrip("/")


def normalise_url(url: str) -> str:
    trimmed = url
    if trimmed.startswith("https://graph.microsoft.com/"):
        trimmed = trimmed[len("https://graph.microsoft.com/") :]
    elif trimmed.startswith("http://graph.microsoft.com/"):
        trimmed = trimmed[len("http://graph.microsoft.com/") :]

    components = trimmed.split("/", 1)
    if len(components) == 2 and components[0].lower() in {"beta", "v1.0", "v1"}:
        trimmed = components[1]
    if "?" in trimmed:
        trimmed = trimmed.split("?", 1)[0]
    if "#" in trimmed:
        trimmed = trimmed.split("#", 1)[0]
    trimmed = trimmed.lstrip("/")
    trimmed = trimmed.rstrip("/")
    trimmed = trimmed.replace("'", "")
    trimmed = trimmed.replace(" ", "")
    trimmed = trimmed.replace("microsoft.graph.", "graph.")
    return trimmed.replace("**", "*")


def is_intune_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in INTUNE_PREFIXES)


def reduce_to_intune_paths(
    paths: Iterable[tuple[str, str]],
) -> dict[str, set[str]]:
    """Utility for building per-version method lookups limited to Intune prefixes."""

    index: dict[str, set[str]] = {}
    for method, path in paths:
        if not is_intune_path(path):
            continue
        index.setdefault(method.upper(), set()).add(path)
    return index
