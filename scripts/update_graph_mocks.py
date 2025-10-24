"""Synchronise Microsoft Graph mock data for test fixtures.

This script downloads canonical mock responses maintained by the Microsoft Graph
community project (https://github.com/waldekmastykarz/graph-mocks) and stores a
compressed subset inside ``tests/graph/mocks/data``. Tests can then rely on the
local dataset without requiring network access while still keeping parity with
upstream samples.

Usage:
    uv run python scripts/update_graph_mocks.py [--ref main]
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import sys
from pathlib import Path
from typing import Final

import httpx


REPO_URL: Final[str] = "https://github.com/waldekmastykarz/graph-mocks"
RAW_BASE: Final[str] = (
    "https://raw.githubusercontent.com/waldekmastykarz/graph-mocks/{ref}/{filename}"
)
DATA_DIR: Final[Path] = Path("tests/graph/mocks/data")

FILES: Final[dict[str, str]] = {
    "graph-beta-proxy-mocks.json": "Official Graph beta mock responses",
    "graph-v1_0-proxy-mocks.json": "Official Graph v1.0 mock responses",
}


def fetch_mock_file(filename: str, ref: str) -> bytes:
    """Download a mock definition file from the upstream repository."""

    url = RAW_BASE.format(ref=ref, filename=filename)
    with httpx.Client(timeout=60.0) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.content


def write_gzip(target: Path, payload: bytes) -> None:
    """Write bytes to disk using deterministic gzip compression."""

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as raw:
        with gzip.GzipFile(
            fileobj=raw,
            mode="wb",
            compresslevel=9,
            mtime=0,
        ) as handle:
            handle.write(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ref",
        default="main",
        help="Git ref (branch, tag, or commit) in the graph-mocks repository.",
    )
    args = parser.parse_args(argv)

    metadata: dict[str, object] = {
        "source_repository": REPO_URL,
        "ref": args.ref,
        "generated_at": dt.datetime.now(tz=dt.UTC).isoformat(),
        "files": {},
    }

    for filename, description in FILES.items():
        payload = fetch_mock_file(filename, args.ref)
        try:
            json.loads(payload)
        except json.JSONDecodeError as exc:  # pragma: no cover - network edge
            raise SystemExit(
                f"Downloaded payload is not valid JSON: {filename}"
            ) from exc

        compressed = DATA_DIR / f"{filename}.gz"
        write_gzip(compressed, payload)
        metadata["files"][filename] = {
            "description": description,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "uncompressed_size": len(payload),
            "compressed_size": compressed.stat().st_size,
        }
        print(
            f"✓ {filename} ({metadata['files'][filename]['compressed_size']} bytes compressed)",  # noqa: T201
        )

    metadata_path = DATA_DIR / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Metadata written to {metadata_path}")  # noqa: T201

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
