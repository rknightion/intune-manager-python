# Contributing Guide

Welcome to the Intune Manager migration project! This repository is optimised for LLM-assisted development—please follow the practices below to keep the process smooth and auditable.

## Workflow Basics
1. **Read `migration.txt` first.** It is the authoritative backlog and status tracker for the Swift → Python migration.
2. **Use `uv` for everything.** Environment creation, dependency changes, linting, tests—no `pip` or manual venvs.
3. **Update AGENT guides.** When creating new modules or changing expectations, edit the nearest `AGENTS.md`.
4. **Prefer `apply_patch`.** Keep diffs focused and human-readable; avoid wholesale rewrites when targeted edits suffice.

## Common Commands
```bash
uv sync                     # install dependencies
uv run intune-manager-lint  # ruff check
uv run intune-manager-fmt   # ruff format
uv run intune-manager-typecheck   # mypy
uv run intune-manager-tests       # pytest (async + Qt support)
```

## Code Standards
- Target Python 3.13 and type annotations everywhere (validated by mypy).
- Keep UI code in `intune_manager.ui`, services in `intune_manager.services`, etc.
- Log meaningful changes in `migration.txt` progress log.
- Before exiting a session, summarise changes and propose next steps for continuity.

## Questions or Decisions
- Capture architectural decisions, blockers, and new tasks inside `migration.txt`.
- Use GitHub issues or ADRs (to be introduced later) for larger discussions.

Thanks for helping deliver the cross-platform Intune Manager experience!
