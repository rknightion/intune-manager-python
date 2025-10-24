## Graph Schema Utilities

### Purpose
- Store compressed OpenAPI documents for Graph v1.0 + beta (sourced from `microsoftgraph/msgraph-metadata`).
- Persist a precomputed Intune-focused path index (`intune-index.json`) derived from those specs for fast contract validation in tests.

### Maintenance
- Refresh files with `uv run python scripts/update_graph_schemas.py [--ref master]`. This updates compressed sources, regenerates the path index, and rewrites metadata hashes in `tests/graph/schemas/data/`.
- Keep `pyyaml` pinned in dev dependencies; the refresh script relies on `yaml.safe_load` when building the index.

### Usage
- Use `load_default_registry()` in tests to check whether a URL (`https://graph.microsoft.com/...`) maps to a documented OpenAPI path for a specific channel using the cached Intune index.
- Normalisation strips host/version, replaces `{param}` segments with `*`, and coalesces legacy `microsoft.graph.*` segments to `graph.*` to align with msgraph-metadata output.
