from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .common import GraphBaseModel, GraphResource


class AuditActor(GraphBaseModel):
    type: str | None = None
    audit_actor_type: str | None = Field(default=None, alias="auditActorType")
    user_permissions: list[str] | None = Field(default=None, alias="userPermissions")
    application_id: str | None = Field(default=None, alias="applicationId")
    application_display_name: str | None = Field(
        default=None, alias="applicationDisplayName"
    )
    user_principal_name: str | None = Field(default=None, alias="userPrincipalName")
    service_principal_name: str | None = Field(
        default=None, alias="servicePrincipalName"
    )
    ip_address: str | None = Field(default=None, alias="ipAddress")
    user_id: str | None = Field(default=None, alias="userId")


class AuditResource(GraphBaseModel):
    display_name: str | None = Field(default=None, alias="displayName")
    type: str | None = None
    audit_resource_type: str | None = Field(default=None, alias="auditResourceType")
    resource_id: str | None = Field(default=None, alias="resourceId")


class AuditEvent(GraphResource):
    display_name: str | None = Field(default=None, alias="displayName")
    component_name: str | None = Field(default=None, alias="componentName")
    activity: str | None = None
    activity_date_time: datetime | None = Field(default=None, alias="activityDateTime")
    activity_type: str | None = Field(default=None, alias="activityType")
    activity_operation_type: str | None = Field(
        default=None, alias="activityOperationType"
    )
    activity_result: str | None = Field(default=None, alias="activityResult")
    correlation_id: str | None = Field(default=None, alias="correlationId")
    category: str | None = None
    actor: AuditActor | None = None
    resources: list[AuditResource] | None = None
