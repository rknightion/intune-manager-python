from __future__ import annotations

import gzip
import json
import re
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any, Iterable

from tests.graph.schemas.utils import normalise_url


@dataclass(slots=True, frozen=True)
class GraphMock:
    method: str
    pattern: str
    example_url: str | None
    response_status: int
    response_headers: tuple[tuple[str, str], ...]
    response_body: Any | None
    source: Path
    version: str
    _compiled: re.Pattern[str]

    def matches(self, url: str) -> bool:
        return bool(self._compiled.fullmatch(url))

    def normalised_path(self) -> str:
        return normalise_url(self.pattern)


class GraphMockRepository:
    """Repository of canonical Microsoft Graph mock responses."""

    def __init__(self, entries: Iterable[GraphMock]) -> None:
        grouped: dict[str, list[GraphMock]] = {}
        for entry in entries:
            grouped.setdefault(entry.method, []).append(entry)
        self._entries = grouped

    @cached_property
    def methods(self) -> tuple[str, ...]:
        return tuple(sorted(self._entries))

    @classmethod
    def from_directory(cls, directory: Path) -> "GraphMockRepository":
        """Load mocks from compressed JSON definitions in the given directory."""

        if not directory.exists():
            raise FileNotFoundError(f"Mock dataset directory missing: {directory}")

        entries: list[GraphMock] = []
        for path in sorted(directory.glob("graph-*-proxy-mocks.json.gz")):
            entries.extend(cls._load_file(path))
        if not entries:
            raise ValueError(
                f"No Graph mock definitions found in {directory!s}; run "
                "'uv run python scripts/update_graph_mocks.py' first.",
            )
        return cls(entries)

    @staticmethod
    def _load_file(path: Path) -> list[GraphMock]:
        with gzip.open(path, "rb") as handle:
            payload = json.load(handle)
        mocks = payload.get("mocks")
        if not isinstance(mocks, list):
            raise ValueError(f"Invalid mock payload in {path!s}")

        version = _detect_version(path.name)
        entries: list[GraphMock] = []
        for raw in mocks:
            request = raw.get("request", {})
            response = raw.get("response", {})
            method = str(request.get("method", "GET")).upper()
            pattern = str(request.get("url"))
            if not pattern:
                continue

            headers: tuple[tuple[str, str], ...] = ()
            raw_headers = response.get("headers") or []
            if isinstance(raw_headers, list):
                cleaned: list[tuple[str, str]] = []
                for header in raw_headers:
                    if not isinstance(header, dict):
                        continue
                    name = header.get("name")
                    value = header.get("value")
                    if isinstance(name, str) and isinstance(value, str):
                        cleaned.append((name, value))
                headers = tuple(cleaned)

            body = response.get("body")
            status_code = int(response.get("statusCode", 200))

            compiled = _compile_pattern(pattern)
            entries.append(
                GraphMock(
                    method=method,
                    pattern=pattern,
                    example_url=_ensure_str(request.get("exampleUrl")),
                    response_status=status_code,
                    response_headers=headers,
                    response_body=body,
                    source=path,
                    version=version,
                    _compiled=compiled,
                ),
            )
        return entries

    def match(self, method: str, url: str) -> GraphMock | None:
        """Return the first mock matching the method and URL."""

        normalised_method = method.upper()
        candidates = self._entries.get(normalised_method)
        if not candidates:
            return None

        for entry in candidates:
            if entry.matches(url):
                return entry
        return None

    def find_by_prefix(self, method: str, prefix: str) -> list[GraphMock]:
        """Return mocks whose patterns share a prefix (for debugging/tests)."""

        normalised_method = method.upper()
        return [
            entry
            for entry in self._entries.get(normalised_method, [])
            if entry.pattern.startswith(prefix)
        ]

    def iter(self, method: str | None = None) -> Iterable[GraphMock]:
        """Iterate over mocks, optionally filtered by HTTP method."""

        if method is None:
            for entries in self._entries.values():
                yield from entries
            return

        yield from self._entries.get(method.upper(), [])


def _detect_version(filename: str) -> str:
    if "beta" in filename:
        return "beta"
    if "v1_0" in filename:
        return "v1.0"
    return "unknown"


def _compile_pattern(pattern: str) -> re.Pattern[str]:
    escaped = []
    for char in pattern:
        if char == "*":
            escaped.append(r"[^?&]*")
        else:
            escaped.append(re.escape(char))
    regex = "".join(escaped)
    return re.compile(rf"^{regex}$")


def _ensure_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"


def load_default_repository() -> GraphMockRepository:
    """Load the repository using the checked-in dataset."""

    return GraphMockRepository.from_directory(DEFAULT_DATA_DIR)
