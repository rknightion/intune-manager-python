# intune_manager.services – AGENT Brief

## Purpose
- Implement business logic for Microsoft Graph and local cache operations.
- Provide thin async facades over repositories and Graph request builders for UI consumption.

## Guidelines
- Keep modules focused per domain (devices, applications, assignments, etc.) and avoid hard UI imports.
- Use shared Graph utilities (`intune_manager.graph`) for network calls and reuse retry/logging hooks.
- Capture new service requirements and API additions in `migration.txt` before major refactors.
