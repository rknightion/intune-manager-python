# intune_manager.config – AGENT Brief

## Purpose
- Manage environment configuration, settings persistence, and feature flags.
- Provide typed access to tenant/client IDs, scope lists, paths, and logging setup.

## Guidelines
- Centralize dotenv and platform-specific config directory handling here.
- Keep secrets retrieval abstract (keyring/secure store) so services remain platform-agnostic.
- Update `migration.txt` when introducing new configuration keys or flows requiring user action.
