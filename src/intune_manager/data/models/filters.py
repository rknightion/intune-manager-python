from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from .common import TimestampedResource


class AssignmentFilterPlatform(StrEnum):
    UNKNOWN = "unknown"
    ANDROID = "android"
    IOS = "ios"
    MACOS = "macOS"
    WINDOWS = "windows"
    WINDOWS_H_N_T = "windowsHolographicForBusiness"


class AssignmentFilter(TimestampedResource):
    display_name: str = Field(alias="displayName")
    description: str | None = None
    platform: AssignmentFilterPlatform | None = None
    filter_rule: str | None = Field(default=None, alias="rule")
    role_scope_tag_ids: list[str] | None = Field(default=None, alias="roleScopeTagIds")
