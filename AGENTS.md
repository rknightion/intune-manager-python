# Intune Manager Python – AGENT Playbook

## Mission
- Make various aspects of administering Microsoft Intune easier by providing a desktop application
- Focus on specific activities that the Intune Web Interface makes time consuming, such as bulk assignments of apps/groups/profiles
- A particular focus on App management

## Project Architecture

### Layered Structure
```
src/intune_manager/
├── auth/          # MSAL + keyring for secure token/secret lifecycle
├── config/        # Settings, env vars, feature flags
├── graph/         # Graph API client (httpx), rate limiting, version switching
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

```

## Operating Procedure
- **Dependency management**: Use `uv` exclusively (uv run, uv sync, uv add); never pip/venv.
- **Code style**: Async-first (asyncio + Qt), fully typed (Python 3.13), tested (pytest), linted (ruff), checked (mypy).
- **Child directories**: Every child folder with responsibility gets an `AGENTS.md` documenting local conventions.
- **Commits**: You MUST NEVER run any git commands yourself to commit code. The only git commands permitted for you to run is diff related commands so you can get additional context but only if strictly necessary

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
- Use custom httpx client with MSAL token injection for direct REST API access.
- Support both v1.0 GA and beta endpoints via per-path version override system.
- Cache responses in SQLModel with configurable TTLs per domain.
- Ensure the onboarding wizard and in-app messages are updated if features you add require additional Graph API Permissions so users can update their scopes

### Domain Boundaries (Mirror Swift architecture)
- **auth**: MSAL token acquisition, keyring secret storage, permission validation
- **config**: Environment setup, dotenv, platform-specific config directories
- **graph**: Graph REST client (httpx+MSAL), rate limiting, pagination, batch operations, version switching
- **data**: Models, SQLite persistence, cache management, repositories
- **services**: Business logic (device sync, app assignment, group membership queries)
- **ui**: PySide6 windows, dialogs, widgets, styling, event orchestration
- **utils**: Shared helpers (logging, async bridging, formatting)
- **cli**: Optional bootstrap/diagnostic commands (thin CLI layer over services)

### Security & Secrets
- Store tenant ID, client ID, redirect URI in env vars or config file (gitignore).
- Store client secrets and user tokens in keyring/OS credential store.
- Never log sensitive values; sanitize auth headers in debug output.

## Development Workflow

### Running the App
- GUI: `uv run intune-manager-app`
- Linting: `uv run intune-manager-lint`
- Type check: `uv run intune-manager-typecheck`
- Tests: `uv run intune-manager-tests`
- Format: `uv run intune-manager-fmt`

### Testing
- Unit tests for domain models and business logic (repositories, services).
- Integration tests for Graph API interactions (mocked endpoints).
- UI tests with pytest-qt for critical user flows.
- Preferring test-driven development for new features.
- Always run the 5 s auto-quit launch smoke test before marking major tasks complete:
  ```bash
  uv run python - <<'PY'
  import threading
  import time
  from PySide6.QtWidgets import QApplication

  from intune_manager import main


  def shutdown() -> None:
      for _ in range(50):
          app = QApplication.instance()
          if app is not None:
              app.quit()
              return
          time.sleep(0.1)
      raise SystemExit("Application did not initialize within timeout")


  timer = threading.Timer(5.0, shutdown)
  timer.start()
  try:
      main()
  finally:
      timer.cancel()
  PY
  ```
  This validates that `intune_manager.main()` starts without runtime errors; resolve any issues before ticking tasks in `migration.txt`.

## Collaboration & Documentation Notes
- **migration.txt**: Update before exiting each session (state, blockers, next steps).
- **Code comments**: Only where context is non-obvious; prefer self-documenting code.

## Cross-References
- See `@intune_manager/ui` for UI layer conventions
- See `@intune_manager/services` for service/business logic patterns
- See `@intune_manager/data` for data layer and persistence
- See `@intune_manager/auth` for authentication and security flows
- See `@intune_manager/graph` for Graph API client patterns
- See `@intune_manager/utils` for reusable helpers
