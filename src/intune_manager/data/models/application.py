from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field

from .assignment import MobileAppAssignment
from .common import TimestampedResource


class MobileAppPlatform(StrEnum):
    UNKNOWN = "unknown"
    WINDOWS = "windows"
    IOS = "ios"
    MACOS = "macOS"
    ANDROID = "android"
    IOS_VPP = "iosVpp"


class MobileAppCategory(TimestampedResource):
    display_name: str = Field(alias="displayName")
    description: str | None = None


class MobileApp(TimestampedResource):
    display_name: str = Field(alias="displayName")
    description: str | None = None
    publisher: str | None = None
    owner: str | None = None
    developer: str | None = None
    information_url: str | None = Field(default=None, alias="informationUrl")
    privacy_information_url: str | None = Field(
        default=None, alias="privacyInformationUrl"
    )
    notes: str | None = None
    upload_state: int | None = Field(default=None, alias="uploadState")
    is_featured: bool | None = Field(default=None, alias="isFeatured")
    platform_type: MobileAppPlatform | None = Field(default=None, alias="platformType")
    is_hidden: bool | None = Field(default=None, alias="isHidden")
    dependent_app_count: int | None = Field(default=None, alias="dependentAppCount")
    superseded_app_count: int | None = Field(default=None, alias="supersededAppCount")
    categories: list[MobileAppCategory] | None = None
    assignments: list[MobileAppAssignment] | None = None
    created_date_time: datetime | None = Field(default=None, alias="createdDateTime")
    last_modified_date_time: datetime | None = Field(
        default=None, alias="lastModifiedDateTime"
    )
    publishing_state: Literal["notPublished", "processing", "published"] | None = Field(
        default=None,
        alias="publishingState",
    )
