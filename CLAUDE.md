# Intune Manager Python – AGENT Playbook

## Mission
- Deliver the cross-platform Intune Manager GUI by migrating the Swift macOS app to Python 3.13 with PySide6.
- Ensure feature parity with the Swift reference while embracing uv-based workflows, MSAL auth, and the official `msgraph-beta-sdk-python` MS graph SDK.
- Treat `migration.txt` as the durable backlog and always update it before exiting a session.

## Project Architecture

### Layered Structure
```
src/intune_manager/
├── auth/          # MSAL + keyring for secure token/secret lifecycle
├── config/        # Settings, env vars, feature flags
├── graph/         # msgraph-beta-sdk wrappers, rate limiting, middleware
├── data/          # Models, SQLModel persistence, repositories, storage
│   ├── models/    # Pydantic domain models (devices, apps, groups, assignments, etc.)
│   ├── repositories/ # Cache-aware data access patterns
│   ├── sql/       # SQLModel schemas, migrations, session management
│   └── storage/   # Binary attachment handling (icons, exports, logs)
├── services/      # Business logic facades over repositories + Graph API
├── ui/            # PySide6 windows, dialogs, widgets, theming
│   ├── main/      # MainWindow, navigation orchestration
│   ├── applications/  # App browser, assignment editor
│   ├── devices/   # Device explorer with detail drawer
│   ├── groups/    # Group membership explorer and editor
│   ├── assignments/ # Bulk assignment workspace
│   ├── dashboard/ # Tenant health overview + quick actions
│   ├── components/ # Reusable PySide6 widgets (overlays, toasts, dialogs)
│   └── settings/  # Configuration, auth, diagnostics
├── utils/         # Shared async tools, formatting, telemetry helpers
└── cli/           # Optional command-line entry points

migration.txt     # Durable backlog + progress log (consult at session start)
AGENTS.md         # This file (project-wide conventions)
```

## Operating Procedure
- **Session start**: Read `migration.txt` to understand current phase and blockers.
- **Dependency management**: Use `uv` exclusively (uv run, uv sync, uv add); never pip/venv.
- **Code style**: Async-first (asyncio + Qt), fully typed (Python 3.13), tested (pytest), linted (ruff), checked (mypy).
- **Child directories**: Every child folder with responsibility gets an `AGENTS.md` documenting local conventions.
- **Commits**: Use meaningful messages referencing `migration.txt` tasks; include context about why, not just what.
- **Session end**: Update `migration.txt` (task state, blockers, discoveries) to preserve context for next session.

## Coding Standards

### Python & Tooling
- Target Python 3.13 syntax with modern async/await, type hints, and f-strings.
- Enforce standards: `ruff check --fix`, `ruff format`, `mypy`, `pytest`.
- All code lives in `src/intune_manager/`; tests in `tests/`.

### Architecture Patterns
- **UI-Service boundary**: Services never import UI modules; UI consumes services via `ServiceRegistry`.
- **Data-Service boundary**: Services use repositories + Graph clients; keep SQL/ORM hidden from services.
- **Async design**: All I/O (Graph, database, disk) is async; use `AsyncBridge` for Qt integration.
- **Signal-driven events**: Prefer Qt signals over callbacks for UI state updates.

### Graph API Access
- Route all Microsoft Graph calls through `intune_manager.graph` (rate limiting, retry, logging).
- Use `msgraph-beta-sdk-python` clients with dependency-injected credentials.
- Cache responses in SQLModel with configurable TTLs per domain.
- Document new scopes or API additions in `migration.txt`.

### Domain Boundaries (Mirror Swift architecture)
- **auth**: MSAL token acquisition, keyring secret storage, permission validation
- **config**: Environment setup, dotenv, platform-specific config directories
- **graph**: Graph SDK wrappers, pagination, batch operations, endpoint utilities
- **data**: Models, SQLite persistence, cache management, repositories
- **services**: Business logic (device sync, app assignment, group membership queries)
- **ui**: PySide6 windows, dialogs, widgets, styling, event orchestration
- **utils**: Shared helpers (logging, async bridging, formatting)
- **cli**: Optional bootstrap/diagnostic commands (thin CLI layer over services)

### Security & Secrets
- Store tenant ID, client ID, redirect URI in env vars or config file (gitignore).
- Store client secrets and user tokens in keyring/OS credential store.
- Never log sensitive values; sanitize auth headers in debug output.
- Use SQLite with file-level encryption for cache database (future enhancement).

## Development Workflow

### Running the App
- GUI: `uv run intune-manager-app`
- Linting: `uv run intune-manager-lint`
- Type check: `uv run intune-manager-typecheck`
- Tests: `uv run intune-manager-tests`
- Format: `uv run intune-manager-fmt`

### Feature Parity Checklist
- Bulk assignments (apps to groups with intent + filters)
- Device detail drawer (tabs: Overview, Hardware, Network, Security, Installed Apps)
- Group membership explorer with add/remove flows
- Audit log browser with export
- `.mobileconfig` export support
- Cache status display + manual refresh
- Settings: tenant config, MSAL sign-in, permission diagnostics

### Testing
- Unit tests for domain models and business logic (repositories, services).
- Integration tests for Graph API interactions (mocked endpoints).
- UI tests with pytest-qt for critical user flows.
- Preferring test-driven development for new features.

## Collaboration & Documentation Notes
- **migration.txt**: Update before exiting each session (state, blockers, next steps).
- **AGENTS.md (child dirs)**: Document module-specific conventions, architecture patterns, cross-module dependencies.
- **Code comments**: Only where context is non-obvious; prefer self-documenting code.
- **Handoff**: Summarize progress and recommend next steps to keep momentum across sessions.

## Cross-References
- See `@intune_manager/ui` for UI layer conventions
- See `@intune_manager/services` for service/business logic patterns
- See `@intune_manager/data` for data layer and persistence
- See `@intune_manager/auth` for authentication and security flows
- See `@intune_manager/graph` for Graph API client patterns
- See `@intune_manager/utils` for reusable helpers
