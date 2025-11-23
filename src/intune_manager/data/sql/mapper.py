from __future__ import annotations

from datetime import UTC, datetime
from typing import Iterable

from intune_manager.data.models import (
    AssignmentFilter,
    AssignmentTarget,
    ConfigurationProfile,
    DirectoryGroup,
    GroupMember,
    ManagedDevice,
    MobileApp,
    MobileAppAssignment,
    AuditEvent,
)

from .models import (
    AssignmentFilterRecord,
    AuditEventRecord,
    ConfigurationProfileRecord,
    DeviceRecord,
    GroupMemberRecord,
    GroupRecord,
    MobileAppAssignmentRecord,
    MobileAppRecord,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def device_to_record(
    device: ManagedDevice, *, tenant_id: str | None = None
) -> DeviceRecord:
    return DeviceRecord(
        id=device.id,
        tenant_id=tenant_id,
        device_name=device.device_name,
        operating_system=device.operating_system,
        compliance_state=device.compliance_state,
        management_state=device.management_state,
        ownership=device.ownership,
        user_principal_name=device.user_principal_name,
        last_sync_date_time=device.last_sync_date_time,
        updated_at=_utc_now(),
        payload=device.to_graph(),
    )


def record_to_device(record: DeviceRecord) -> ManagedDevice:
    payload = record.payload or {}
    payload.setdefault("id", record.id)
    return ManagedDevice.from_graph(payload)


def mobile_app_to_record(
    app: MobileApp, *, tenant_id: str | None = None
) -> MobileAppRecord:
    return MobileAppRecord(
        id=app.id,
        tenant_id=tenant_id,
        display_name=app.display_name,
        publisher=app.publisher,
        platform=getattr(app.platform_type, "value", app.platform_type),
        app_type=app.app_type,
        publishing_state=app.publishing_state,
        last_modified_date_time=app.last_modified_date_time,
        updated_at=_utc_now(),
        payload=app.to_graph(),
    )


def record_to_mobile_app(record: MobileAppRecord) -> MobileApp:
    payload = record.payload or {}
    payload.setdefault("id", record.id)
    # Rehydrate derived fields when missing from payload
    if record.app_type and "app_type" not in payload:
        payload["app_type"] = record.app_type
    if record.platform and "platformType" not in payload:
        payload["platformType"] = record.platform
    return MobileApp.from_graph(payload)


def group_to_record(
    group: DirectoryGroup, *, tenant_id: str | None = None
) -> GroupRecord:
    return GroupRecord(
        id=group.id,
        tenant_id=tenant_id,
        display_name=group.display_name,
        mail=group.mail,
        mail_enabled=group.mail_enabled,
        security_enabled=group.security_enabled,
        group_types=group.group_types,
        updated_at=_utc_now(),
        payload=group.to_graph(),
    )


def record_to_group(record: GroupRecord) -> DirectoryGroup:
    payload = record.payload or {}
    payload.setdefault("id", record.id)
    return DirectoryGroup.from_graph(payload)


def configuration_to_record(
    profile: ConfigurationProfile,
    *,
    tenant_id: str | None = None,
) -> ConfigurationProfileRecord:
    return ConfigurationProfileRecord(
        id=profile.id,
        tenant_id=tenant_id,
        display_name=profile.display_name,
        profile_type=getattr(profile.profile_type, "value", profile.profile_type),
        platform=getattr(profile.platform_type, "value", profile.platform_type),
        version=profile.version,
        last_modified_date_time=profile.last_modified_date_time,
        updated_at=_utc_now(),
        payload=profile.to_graph(),
    )


def record_to_configuration(record: ConfigurationProfileRecord) -> ConfigurationProfile:
    payload = record.payload or {}
    payload.setdefault("id", record.id)
    return ConfigurationProfile.from_graph(payload)


def audit_event_to_record(
    event: AuditEvent, *, tenant_id: str | None = None
) -> AuditEventRecord:
    return AuditEventRecord(
        id=event.id,
        tenant_id=tenant_id,
        activity=event.activity,
        category=event.category,
        activity_date_time=event.activity_date_time,
        correlation_id=event.correlation_id,
        updated_at=_utc_now(),
        payload=event.to_graph(),
    )


def record_to_audit_event(record: AuditEventRecord) -> AuditEvent:
    payload = record.payload or {}
    payload.setdefault("id", record.id)
    return AuditEvent.from_graph(payload)


def assignment_filter_to_record(
    assignment_filter: AssignmentFilter,
    *,
    tenant_id: str | None = None,
) -> AssignmentFilterRecord:
    return AssignmentFilterRecord(
        id=assignment_filter.id,
        tenant_id=tenant_id,
        display_name=assignment_filter.display_name,
        platform=getattr(
            assignment_filter.platform, "value", assignment_filter.platform
        ),
        updated_at=_utc_now(),
        payload=assignment_filter.to_graph(),
    )


def record_to_assignment_filter(record: AssignmentFilterRecord) -> AssignmentFilter:
    payload = record.payload or {}
    payload.setdefault("id", record.id)
    return AssignmentFilter.from_graph(payload)


def assignments_to_records(
    app_id: str,
    assignments: Iterable[MobileAppAssignment],
    *,
    tenant_id: str | None = None,
) -> list[MobileAppAssignmentRecord]:
    records: list[MobileAppAssignmentRecord] = []
    for assignment in assignments:
        target: AssignmentTarget = assignment.target
        target_id = getattr(target, "group_id", None)
        filter_id = getattr(target, "assignment_filter_id", None)
        filter_type = getattr(target, "assignment_filter_type", None)
        target_type = getattr(target, "odata_type", None)
        records.append(
            MobileAppAssignmentRecord(
                id=assignment.id,
                app_id=app_id,
                tenant_id=tenant_id,
                target_id=target_id,
                target_type=target_type,
                intent=assignment.intent,
                filter_id=filter_id,
                filter_type=filter_type,
                updated_at=_utc_now(),
                payload=assignment.to_graph(),
            ),
        )
    return records


def record_to_assignment(record: MobileAppAssignmentRecord) -> MobileAppAssignment:
    payload = record.payload or {}
    payload.setdefault("id", record.id)
    return MobileAppAssignment.from_graph(payload)


def group_members_to_records(
    group_id: str,
    members: Iterable[GroupMember],
    *,
    tenant_id: str | None = None,
    is_owner: bool = False,
) -> list[GroupMemberRecord]:
    records: list[GroupMemberRecord] = []
    for member in members:
        records.append(
            GroupMemberRecord(
                group_id=group_id,
                member_id=member.id,
                tenant_id=tenant_id,
                is_owner=is_owner,
                display_name=member.display_name,
                user_principal_name=member.user_principal_name,
                mail=member.mail,
                odata_type=member.odata_type,
                updated_at=_utc_now(),
                payload=member.to_graph(),
            )
        )
    return records


def record_to_group_member(record: GroupMemberRecord) -> GroupMember:
    payload = record.payload or {}
    payload.setdefault("id", record.member_id)
    return GroupMember.from_graph(payload)


__all__ = [
    "device_to_record",
    "record_to_device",
    "mobile_app_to_record",
    "record_to_mobile_app",
    "group_to_record",
    "record_to_group",
    "group_members_to_records",
    "record_to_group_member",
    "configuration_to_record",
    "record_to_configuration",
    "audit_event_to_record",
    "record_to_audit_event",
    "assignment_filter_to_record",
    "record_to_assignment_filter",
    "assignments_to_records",
    "record_to_assignment",
]
