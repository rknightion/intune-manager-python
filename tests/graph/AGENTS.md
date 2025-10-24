## Graph Test Conventions

### Purpose
- House integration/unit tests covering `intune_manager.graph` package behaviour (rate limiting, client interactions, mock infrastructure).
- Provide canonical Graph API mocks for offline tests sourced from Microsoft Graph community datasets.

### Fixtures
- `graph_mock_repository` (session scope) loads compressed mocks from `tests/graph/mocks/data/`.
- `graph_mock_respx` registers a catch-all `respx` router that auto-serves responses based on upstream definitions. It asserts that every request matches a known mock.
- `ensure_graph_mock` helper fixture activates the official responder for a specific method/url pair, skipping tests automatically when upstream mocks are missing.

### Updating Mock Data
- Run `uv run python scripts/update_graph_mocks.py [--ref <git-ref>]` to refresh the dataset from https://github.com/waldekmastykarz/graph-mocks.
- The script writes compressed JSON files plus `metadata.json` with source checksum information. Commit these changes alongside tests relying on new endpoints.

### Adding Coverage
- Prefer using `graph_mock_respx` over hand-crafted responses so tests stay aligned with official contracts.
- When no canonical mock exists, add targeted fixtures in `tests/graph/mocks/data/` and document upstream issue in `migration.txt`.
