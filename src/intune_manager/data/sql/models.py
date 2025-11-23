from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SchemaVersion(SQLModel, table=True):
    """Tracks the current schema version applied to the database."""

    key: str = Field(default="schema_version", primary_key=True)
    version: int = Field(index=True)
    applied_at: datetime = Field(default_factory=_utc_now, nullable=False)


class CacheEntry(SQLModel, table=True):
    """Metadata for cached Graph collections."""

    __tablename__ = "cache_entries"

    resource: str = Field(primary_key=True)
    scope: str = Field(primary_key=True)
    tenant_id: str | None = Field(default=None, index=True)
    last_refresh: datetime | None = Field(default=None, index=True)
    expires_at: datetime | None = Field(default=None, index=True)
    item_count: int | None = Field(default=None)


class DeviceRecord(SQLModel, table=True):
    """Stored managed device with a denormalised JSON payload."""

    __tablename__ = "devices"

    id: str = Field(primary_key=True)
    tenant_id: str | None = Field(default=None, index=True)
    device_name: str | None = Field(default=None, index=True)
    operating_system: str | None = Field(default=None, index=True)
    compliance_state: str | None = Field(default=None, index=True)
    management_state: str | None = Field(default=None, index=True)
    ownership: str | None = Field(default=None, index=True)
    user_principal_name: str | None = Field(default=None, index=True)
    last_sync_date_time: datetime | None = Field(default=None, index=True)
    updated_at: datetime = Field(default_factory=_utc_now, nullable=False)
    payload: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))


class MobileAppRecord(SQLModel, table=True):
    """Stored mobile app metadata with assignment summary."""

    __tablename__ = "mobile_apps"

    id: str = Field(primary_key=True)
    tenant_id: str | None = Field(default=None, index=True)
    display_name: str | None = Field(default=None, index=True)
    publisher: str | None = Field(default=None, index=True)
    platform: str | None = Field(default=None, index=True)
    app_type: str | None = Field(default=None, index=True)  # Simplified type: Store, LOB, VPP, etc.
    publishing_state: str | None = Field(default=None, index=True)
    last_modified_date_time: datetime | None = Field(default=None, index=True)
    updated_at: datetime = Field(default_factory=_utc_now, nullable=False)
    payload: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))


class GroupRecord(SQLModel, table=True):
    """Azure AD group snapshot."""

    __tablename__ = "groups"

    id: str = Field(primary_key=True)
    tenant_id: str | None = Field(default=None, index=True)
    display_name: str | None = Field(default=None, index=True)
    mail: str | None = Field(default=None, index=True)
    mail_enabled: bool | None = Field(default=None, index=True)
    security_enabled: bool | None = Field(default=None, index=True)
    group_types: list[str] | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    updated_at: datetime = Field(default_factory=_utc_now, nullable=False)
    payload: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))


class MobileAppAssignmentRecord(SQLModel, table=True):
    """Link table for app assignments to groups and filters."""

    __tablename__ = "mobile_app_assignments"

    id: str = Field(primary_key=True)
    app_id: str = Field(index=True)
    tenant_id: str | None = Field(default=None, index=True)
    target_id: str | None = Field(default=None, index=True)
    target_type: str | None = Field(default=None, index=True)
    intent: str | None = Field(default=None, index=True)
    filter_id: str | None = Field(default=None, index=True)
    filter_type: str | None = Field(default=None, index=True)  # include, exclude, or none
    updated_at: datetime = Field(default_factory=_utc_now, nullable=False)
    payload: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))


class ConfigurationProfileRecord(SQLModel, table=True):
    """Device configuration profile snapshot."""

    __tablename__ = "configuration_profiles"

    id: str = Field(primary_key=True)
    tenant_id: str | None = Field(default=None, index=True)
    display_name: str | None = Field(default=None, index=True)
    profile_type: str | None = Field(default=None, index=True)
    platform: str | None = Field(default=None, index=True)
    version: int | None = Field(default=None)
    last_modified_date_time: datetime | None = Field(default=None, index=True)
    updated_at: datetime = Field(default_factory=_utc_now, nullable=False)
    payload: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))


class AuditEventRecord(SQLModel, table=True):
    """Audit event snapshot for in-app reporting."""

    __tablename__ = "audit_events"

    id: str = Field(primary_key=True)
    tenant_id: str | None = Field(default=None, index=True)
    activity: str | None = Field(default=None, index=True)
    category: str | None = Field(default=None, index=True)
    activity_date_time: datetime | None = Field(default=None, index=True)
    correlation_id: str | None = Field(default=None, index=True)
    updated_at: datetime = Field(default_factory=_utc_now, nullable=False)
    payload: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))


class AssignmentFilterRecord(SQLModel, table=True):
    """Assignment filter snapshot for targeting metadata."""

    __tablename__ = "assignment_filters"

    id: str = Field(primary_key=True)
    tenant_id: str | None = Field(default=None, index=True)
    display_name: str | None = Field(default=None, index=True)
    platform: str | None = Field(default=None, index=True)
    updated_at: datetime = Field(default_factory=_utc_now, nullable=False)
    payload: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))


class GroupMemberRecord(SQLModel, table=True):
    """Group member/owner snapshot with composite key."""

    __tablename__ = "group_members"

    group_id: str = Field(primary_key=True, index=True)
    member_id: str = Field(primary_key=True, index=True)
    tenant_id: str | None = Field(default=None, index=True)
    is_owner: bool = Field(default=False, index=True)
    display_name: str | None = Field(default=None, index=True)
    user_principal_name: str | None = Field(default=None, index=True)
    mail: str | None = Field(default=None)
    odata_type: str | None = Field(default=None)
    updated_at: datetime = Field(default_factory=_utc_now, nullable=False)
    payload: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
