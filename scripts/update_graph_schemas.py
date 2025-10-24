"""Download Microsoft Graph OpenAPI schemas for offline validation.

This script pulls the large `openapi.yaml` definitions from the official
`microsoftgraph/msgraph-metadata` repository (v1.0 + beta variants) and stores
them compressed under ``tests/graph/schemas/data``. Tests can then validate our
mock dataset against the authoritative contract without network access.

Usage:
    uv run python scripts/update_graph_schemas.py [--ref master]
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path
from typing import Final

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.graph.schemas.utils import normalise_openapi_path, reduce_to_intune_paths


REPO_URL: Final[str] = "https://github.com/microsoftgraph/msgraph-metadata"
RAW_BASE: Final[str] = (
    "https://raw.githubusercontent.com/microsoftgraph/msgraph-metadata/{ref}/openapi/{channel}/openapi.yaml"
)
DATA_DIR: Final[Path] = Path("tests/graph/schemas/data")

CHANNELS: Final[tuple[str, ...]] = ("v1.0", "beta")


def fetch_schema(channel: str, ref: str) -> bytes:
    url = RAW_BASE.format(ref=ref, channel=channel)
    with httpx.Client(timeout=120.0) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.content


def write_gzip(target: Path, payload: bytes) -> None:
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
        default="master",
        help="Git ref (branch, tag, or commit) in the msgraph-metadata repository.",
    )
    args = parser.parse_args(argv)

    metadata: dict[str, object] = {
        "source_repository": REPO_URL,
        "ref": args.ref,
        "generated_at": dt.datetime.now(tz=dt.UTC).isoformat(),
        "files": {},
    }
    index: dict[str, dict[str, list[str]]] = {}

    for channel in CHANNELS:
        payload = fetch_schema(channel, args.ref)
        compressed_path = DATA_DIR / f"{channel}-openapi.yaml.gz"
        write_gzip(compressed_path, payload)

        document = yaml.safe_load(payload)
        raw_paths = document.get("paths", {})
        entries: list[tuple[str, str]] = []
        if isinstance(raw_paths, dict):
            for path, operations in raw_paths.items():
                if not isinstance(operations, dict):
                    continue
                normalised_path = normalise_openapi_path(path)
                for method in operations:
                    entries.append((method.upper(), normalised_path))
        intune_index = reduce_to_intune_paths(entries)
        index[channel] = {
            method: sorted(paths) for method, paths in sorted(intune_index.items())
        }

        metadata["files"][channel] = {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "uncompressed_size": len(payload),
            "compressed_size": compressed_path.stat().st_size,
        }
        print(  # noqa: T201
            f"✓ {channel} schema ({metadata['files'][channel]['compressed_size']} bytes compressed)",
        )

    index_path = DATA_DIR / "intune-index.json"
    index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")

    metadata["intune_index"] = str(index_path)
    metadata_path = DATA_DIR / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Metadata written to {metadata_path}")  # noqa: T201
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
