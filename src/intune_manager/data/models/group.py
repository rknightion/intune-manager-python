from __future__ import annotations

from enum import StrEnum

from pydantic import AliasChoices, Field

from .common import GraphResource, TimestampedResource


class GroupType(StrEnum):
    UNIFIED = "Unified"
    SECURITY = "Security"
    DYNAMIC_MEMBERSHIP = "DynamicMembership"


class DirectoryGroup(TimestampedResource):
    display_name: str = Field(
        alias="displayName",
        validation_alias=AliasChoices("displayName", "name"),
    )
    description: str | None = None
    mail: str | None = None
    mail_nickname: str | None = Field(default=None, alias="mailNickname")
    mail_enabled: bool | None = Field(default=None, alias="mailEnabled")
    security_enabled: bool | None = Field(default=None, alias="securityEnabled")
    group_types: list[str] | None = Field(default=None, alias="groupTypes")
    membership_rule: str | None = Field(default=None, alias="membershipRule")
    membership_rule_processing_state: str | None = Field(
        default=None,
        alias="membershipRuleProcessingState",
    )


class GroupMember(GraphResource):
    display_name: str | None = Field(
        default=None,
        alias="displayName",
        validation_alias=AliasChoices("displayName", "name"),
    )
    user_principal_name: str | None = Field(default=None, alias="userPrincipalName")
    mail: str | None = Field(default=None, alias="mail")
    odata_type: str | None = Field(default=None, alias="@odata.type")
