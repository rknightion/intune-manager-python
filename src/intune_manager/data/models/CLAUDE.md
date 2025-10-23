# intune_manager.data.models – AGENT Brief

## Purpose
- Define domain models using Pydantic with full Microsoft Graph alias mapping.
- Provide validated, type-safe data structures for devices, applications, groups, assignments, configurations, filters, and audit logs.
- Bridge Graph API responses to in-app business logic without UI coupling.

## Module Contents

### Core Models
- **`device.py`**: `ManagedDevice` with compliance/management states, hardware details, network info, user context
- **`application.py`**: `MobileApp` with platform, publisher, assignments, publishing state
- **`group.py`**: `DirectoryGroup` (security/mail/unified variants)
- **`assignment.py`**: `MobileAppAssignment` with intent (Available/Required/Uninstall), settings per target group
- **`configuration.py`**: `ConfigurationProfile` for device configuration policies
- **`filters.py`**: `AssignmentFilter` for assignment targeting rules
- **`audit.py`**: `AuditEvent` for compliance and admin action logs
- **`common.py`**: Shared enums and types (compliance states, management states, assignment intents)

## Conventions
- All models inherit from `BaseModel` and use Graph API aliases via `Field(alias="...")`
- Leverage `model_validate()` for Graph payload ingestion; preserve raw JSON in SQLModel records
- Use frozen models where state mutation should be prevented
- Document enum variants in code comments for clarity (e.g., compliance/management state strings)
- Avoid UI imports; keep models pure domain logic

## Guidelines
- When adding new fields, include Graph API alias mapping immediately
- Validate constraints in model methods (e.g., email formatting, date ranges)
- Use discriminated unions for polymorphic types (e.g., filter rules, assignment targets)
- Update `migration.txt` when introducing new models or breaking schema changes
- Keep models composable; avoid circular dependencies with data layer

## Related Modules
- See `@intune_manager/data/repositories` for persistence and cache management
- See `@intune_manager/data/sql` for SQLModel table definitions and migrations
- See `@intune_manager/services` for business logic built on these models
