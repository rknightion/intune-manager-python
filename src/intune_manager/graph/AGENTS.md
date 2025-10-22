# intune_manager.graph – AGENT Brief

## Purpose
- Wrap `msgraph-beta-sdk` clients with app-specific factories, middleware, and telemetry.
- Surface batch/pagination helpers, rate limiting, and endpoint utilities shared across services.

## Guidelines
- Centralize authentication injection and base URLs (beta vs v1.0) to keep services simple.
- Reuse logging conventions defined in `intune_manager.config` and `utils`.
- Record new Graph scopes or middleware decisions in `migration.txt` for visibility.
