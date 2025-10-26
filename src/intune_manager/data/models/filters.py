from __future__ import annotations

from enum import StrEnum

from pydantic import AliasChoices, Field

from .common import TimestampedResource


class AssignmentFilterPlatform(StrEnum):
    UNKNOWN = "unknown"
    ANDROID = "android"
    IOS = "iOS"
    MACOS = "macOS"
    WINDOWS = "windows"
    WINDOWS_HOLOGRAPHIC_FOR_BUSINESS = "windowsHolographicForBusiness"

    @classmethod
    def _missing_(cls, value: object):
        if isinstance(value, str):
            normalised = value.lower()
            for member in cls:
                if member.value.lower() == normalised:
                    return member
        return None


class AssignmentFilter(TimestampedResource):
    display_name: str = Field(
        alias="displayName",
        validation_alias=AliasChoices("displayName", "name"),
    )
    description: str | None = None
    platform: AssignmentFilterPlatform | None = None
    filter_rule: str | None = Field(default=None, alias="rule")
    role_scope_tag_ids: list[str] | None = Field(default=None, alias="roleScopeTagIds")
