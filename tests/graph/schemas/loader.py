from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from .utils import normalise_url


class GraphSchemaRegistry:
    """Fast lookup helper backed by a precomputed Intune path index."""

    def __init__(self, data: Mapping[str, Mapping[str, list[str]]]) -> None:
        registry: dict[str, dict[str, set[str]]] = {}
        for version, methods in data.items():
            version_registry: dict[str, set[str]] = {}
            for method, paths in methods.items():
                version_registry[method.upper()] = {path for path in paths}
            registry[version] = version_registry
        self._registry = registry

    def has_operation(self, version: str, method: str, path: str) -> bool:
        version_registry = self._registry.get(version)
        if not version_registry:
            return False
        candidates = version_registry.get(method.upper())
        if not candidates:
            return False
        return normalise_url(path) in candidates

    def methods_for_version(self, version: str) -> tuple[str, ...]:
        return tuple(sorted(self._registry.get(version, ())))


_DEFAULT_INDEX = None


def load_default_registry() -> GraphSchemaRegistry:
    global _DEFAULT_INDEX
    if _DEFAULT_INDEX is None:
        data_dir = Path(__file__).resolve().parent / "data"
        index_path = data_dir / "intune-index.json"
        with index_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        _DEFAULT_INDEX = GraphSchemaRegistry(data)
    return _DEFAULT_INDEX
