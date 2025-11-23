from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import AliasChoices, Field, model_validator

from intune_manager.utils.app_types import extract_app_type

from .assignment import MobileAppAssignment
from .common import TimestampedResource


class MobileAppPlatform(StrEnum):
    UNKNOWN = "unknown"
    WINDOWS = "windows"
    IOS = "ios"
    MACOS = "macOS"
    ANDROID = "android"
    IOS_VPP = "iosVpp"

    @classmethod
    def _missing_(cls, value: object):
        if isinstance(value, str):
            normalised = value.lower()
            for member in cls:
                if member.value.lower() == normalised:
                    return member
        return None


class MobileAppCategory(TimestampedResource):
    display_name: str = Field(
        alias="displayName",
        validation_alias=AliasChoices("displayName", "name"),
    )
    description: str | None = None


class MobileApp(TimestampedResource):
    display_name: str = Field(
        alias="displayName",
        validation_alias=AliasChoices("displayName", "name"),
    )
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
    app_type: str | None = None  # Extracted from @odata.type (e.g., "Store", "LOB", "VPP")
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

    # Priority 1: Base fields (all app types)
    large_icon: dict[str, Any] | None = Field(default=None, alias="largeIcon")
    is_assigned: bool | None = Field(default=None, alias="isAssigned")
    role_scope_tag_ids: list[str] | None = Field(default=None, alias="roleScopeTagIds")
    superseding_app_count: int | None = Field(
        default=None, alias="supersedingAppCount"
    )

    # Priority 2: iOS VPP fields
    bundle_id: str | None = Field(default=None, alias="bundleId")
    used_license_count: int | None = Field(default=None, alias="usedLicenseCount")
    total_license_count: int | None = Field(default=None, alias="totalLicenseCount")
    release_date_time: datetime | None = Field(default=None, alias="releaseDateTime")
    app_store_url: str | None = Field(default=None, alias="appStoreUrl")
    licensing_type: dict[str, Any] | None = Field(default=None, alias="licensingType")
    applicable_device_type: dict[str, Any] | None = Field(
        default=None, alias="applicableDeviceType"
    )
    vpp_token_organization_name: str | None = Field(
        default=None, alias="vppTokenOrganizationName"
    )
    vpp_token_account_type: str | None = Field(
        default=None, alias="vppTokenAccountType"
    )
    vpp_token_apple_id: str | None = Field(default=None, alias="vppTokenAppleId")
    vpp_token_display_name: str | None = Field(
        default=None, alias="vppTokenDisplayName"
    )
    vpp_token_id: str | None = Field(default=None, alias="vppTokenId")

    # Priority 3: LOB app fields (iOS, Android, Windows LOB)
    committed_content_version: str | None = Field(
        default=None, alias="committedContentVersion"
    )
    file_name: str | None = Field(default=None, alias="fileName")
    size: int | None = Field(
        default=None, alias="size"
    )  # bytes, read-only from Graph

    # Priority 4: Windows app fields
    applicable_architectures: str | None = Field(
        default=None, alias="applicableArchitectures"
    )
    identity_name: str | None = Field(default=None, alias="identityName")
    identity_publisher_hash: str | None = Field(
        default=None, alias="identityPublisherHash"
    )
    identity_resource_identifier: str | None = Field(
        default=None, alias="identityResourceIdentifier"
    )
    is_bundle: bool | None = Field(default=None, alias="isBundle")
    minimum_supported_operating_system: dict[str, Any] | None = Field(
        default=None, alias="minimumSupportedOperatingSystem"
    )

    # Priority 5: Win32 LOB app fields
    setup_file_path: str | None = Field(default=None, alias="setupFilePath")
    minimum_supported_windows_release: str | None = Field(
        default=None, alias="minimumSupportedWindowsRelease"
    )
    display_version: str | None = Field(default=None, alias="displayVersion")

    # Priority 6: Android app fields
    package_id: str | None = Field(default=None, alias="packageId")
    version_name: str | None = Field(default=None, alias="versionName")
    version_code: str | None = Field(default=None, alias="versionCode")
    minimum_supported_android_operating_system: dict[str, Any] | None = Field(
        default=None, alias="minimumSupportedOperatingSystem"
    )
    app_availability: str | None = Field(default=None, alias="appAvailability")
    version: str | None = Field(default=None, alias="version")

    @model_validator(mode="before")
    @classmethod
    def _extract_platform_and_type_from_odata_type(cls, data: Any) -> Any:
        """Extract platform and app type from @odata.type if missing.

        Graph API returns @odata.type like '#microsoft.graph.iosStoreApp'
        which contains both platform and app type information. This validator
        extracts both and sets platformType and app_type if not already present.
        """
        if not isinstance(data, dict):
            return data

        odata_type = data.get("@odata.type", "")
        if not isinstance(odata_type, str):
            return data

        # Extract platform from @odata.type if platformType is missing
        # Examples:
        #   #microsoft.graph.iosStoreApp -> ios
        #   #microsoft.graph.macOSOfficeSuiteApp -> macOS
        #   #microsoft.graph.windowsMobileMSI -> windows
        #   #microsoft.graph.androidStoreApp -> android
        if data.get("platformType") is None:
            platform = None
            odata_lower = odata_type.lower()

            if "ios" in odata_lower:
                platform = "ios"
            elif "macos" in odata_lower or "macosx" in odata_lower:
                platform = "macOS"
            elif "windows" in odata_lower or "win32" in odata_lower or "win10" in odata_lower:
                platform = "windows"
            elif "android" in odata_lower:
                platform = "android"
            elif "web" in odata_lower:
                platform = "unknown"  # Web apps don't have a specific platform

            if platform:
                data["platformType"] = platform

        # Extract app type from @odata.type if app_type is missing
        # Examples:
        #   #microsoft.graph.iosStoreApp -> "Store"
        #   #microsoft.graph.win32LobApp -> "LOB"
        #   #microsoft.graph.iosVppApp -> "VPP"
        if data.get("app_type") is None:
            app_type = extract_app_type(odata_type)
            if app_type:
                data["app_type"] = app_type

        return data
