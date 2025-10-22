# Intune Manager Python – AGENT Playbook

## Mission
- Deliver the cross-platform Intune Manager GUI by migrating the Swift macOS app to Python 3.13 with PySide6.
- Ensure feature parity with the Swift reference while embracing uv-based workflows, msal auth, and the official `msgraph-sdk-python` MS graph SDK.
- Treat `migration.txt` as the durable backlog and always update it before exiting a session.

## Operating Procedure
- Start every session by reading `migration.txt` and updating task state or adding discoveries.
- Use `uv` for all environment, dependency, lint, and test commands; never fall back to pip/venv.
- Keep development async-first (asyncio + Qt integration) and favor typed, testable modules.
- When touching new directories, add an `AGENTS.md` outlining folder-specific norms.
- Prefer `apply_patch` for edits; keep diffs tight and add concise comments only when context is non-obvious.

## Coding Standards
- Target Python 3.13 syntax, enforce `ruff` + `mypy`, and structure code under `src/intune_manager`.
- Model Microsoft Graph access through `GraphServiceClient` helpers (from `msgraph-beta-sdk-python`) with centralized retry/logging hooks.
- Mirror Swift domain boundaries: auth, services, data, ui, utils. Keep UI logic Qt-centric and publish events via signals.
- Store secrets securely (keyring/OS stores); never commit tenant/client IDs.
- Maintain parity for bulk assignments, `.mobileconfig` handling, audit logs, exports, and cache management.

## Collaboration Notes
- Record significant decisions and blockers in `migration.txt` (Progress Log or new tasks).
- Document new commands/scripts in README updates once Phase 1 scaffolding exists.
- Before ending work, outline next recommended steps in your response to keep context flowing across sessions.
