from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from .common import TimestampedResource


class GroupType(StrEnum):
    UNIFIED = "Unified"
    SECURITY = "Security"
    DYNAMIC_MEMBERSHIP = "DynamicMembership"


class DirectoryGroup(TimestampedResource):
    display_name: str = Field(alias="displayName")
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
