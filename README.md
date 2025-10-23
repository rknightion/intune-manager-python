# Intune Manager (Python Edition)

Cross-platform rewrite of the Intune Manager desktop application using Python 3.13, PySide6, and the Microsoft Graph beta SDK.

## Prerequisites
- **Python**: Managed via `uv` (3.13 baseline). No system `pip` or venv usage.
- **Microsoft Graph access**: Azure AD app registration with required Intune beta scopes (see `migration.txt` Phase 0).
- **Platform dependencies**: Qt runtime libraries are handled by PySide6 wheels; additional packaging prerequisites will be documented in Phase 9.

## Quick Start
1. Sync dependencies: `uv sync`
2. Launch placeholder app stub: `uv run intune-manager-app`

## Authentication Setup
- Update tenant/client settings via future configuration UI or directly in `settings.env` (managed by `SettingsManager`).
- Tokens are cached in the runtime directory and protected secrets (e.g., optional client secrets) are stored via OS keyring.
- Auth flows rely on MSAL interactive sign-in; ensure default browser access is permitted.

## Developer Scripts
- `uv run intune-manager-lint` – Ruff static analysis
- `uv run intune-manager-fmt` – Ruff formatter
- `uv run intune-manager-typecheck` – Mypy type checking
- `uv run intune-manager-tests` – Pytest suite (includes pytest-asyncio/pytest-qt)

## Project Layout
```
src/intune_manager/
  auth/       # MSAL flows, permission checks, secure storage
  services/   # Graph-powered business logic and orchestration
  data/       # SQLModel persistence and caching
  graph/      # Graph REST client (httpx+MSAL), rate limiting, batching
  ui/         # PySide6 windows, widgets, and layouts
  config/     # Settings management and environment handling
  utils/      # Shared helpers and infrastructure utilities
  cli/        # Optional command-line tools / diagnostics
```
Each subpackage contains an `AGENTS.md` file describing expectations for LLM-driven development within that area.

## Working Notes
- All long-term planning and task tracking lives in `migration.txt`. Update it whenever scope changes or milestones complete.
- Favor async-first patterns and update AGENT guides as architecture evolves.
- Packaging, CI, and distribution workflows will be introduced in later migration phases.
