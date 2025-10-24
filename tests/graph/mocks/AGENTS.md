## Graph Mock Infrastructure

### Responsibilities
- Store compressed Microsoft Graph mock datasets under `data/`.
- Provide helper classes to load datasets and register `respx` responders during tests.

### Key Modules
- `repository.py`: Parses upstream mock JSON, normalises header/body shapes, and offers lookup helpers.
- `responder.py`: Bridges repository entries into `httpx` responses with optional strictness controls.

### Maintenance
- Refresh datasets with `uv run python scripts/update_graph_mocks.py`. The script updates `metadata.json` with source hashes for traceability.
- When new endpoints are required, prefer contributing upstream to `graph-mocks`. If immediate coverage is needed, add targeted fixtures locally and record the delta in `migration.txt`.

