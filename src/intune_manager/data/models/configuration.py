from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from .assignment import AssignmentTarget
from .common import GraphResource, TimestampedResource


class ConfigurationPlatform(StrEnum):
    ANDROID = "android"
    IOS = "ios"
    MACOS = "macOS"
    WINDOWS10 = "windows10"
    ANDROID_ENTERPRISE = "androidEnterprise"
    ANDROID_WORK_PROFILE = "androidWorkProfile"


class ConfigurationProfileType(StrEnum):
    DEVICE_CONFIGURATION = "deviceConfiguration"
    SETTINGS_CATALOG = "settingsCatalog"
    TEMPLATE = "template"
    CUSTOM = "custom"
    COMPLIANCE_POLICY = "compliancePolicy"
    ADMINISTRATIVE_TEMPLATE = "administrativeTemplate"


class SettingValueType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    CHOICE = "choice"
    MULTI_CHOICE = "multiChoice"
    COMPLEX = "complex"
    COLLECTION = "collection"


class SettingApplicability(GraphResource):
    platform: str | None = None
    min_os_version: str | None = Field(default=None, alias="minOSVersion")
    max_os_version: str | None = Field(default=None, alias="maxOSVersion")
    technologies: list[str] | None = None


class ConfigurationSetting(GraphResource):
    setting_definition_id: str = Field(alias="settingDefinitionId")
    display_name: str = Field(alias="displayName")
    setting_description: str | None = Field(default=None, alias="description")
    value_type: SettingValueType = Field(alias="valueType")
    value: str | None = None
    is_required: bool | None = Field(default=None, alias="isRequired")
    category: str | None = None
    depends_on: list[str] | None = Field(default=None, alias="dependsOn")
    applicability: SettingApplicability | None = None


class ConfigurationAssignment(GraphResource):
    target: AssignmentTarget
    intent: str | None = None


class SettingTemplate(GraphResource):
    display_name: str = Field(alias="displayName")
    description: str | None = None
    platform: ConfigurationPlatform | None = None
    priority: int | None = None


class ConfigurationProfile(TimestampedResource):
    display_name: str = Field(alias="displayName")
    description: str | None = Field(default=None, alias="description")
    version: int | None = None
    platform_type: ConfigurationPlatform | None = Field(
        default=None, alias="platformType"
    )
    profile_type: ConfigurationProfileType | None = Field(
        default=None, alias="profileType"
    )
    template_id: str | None = Field(default=None, alias="templateId")
    template_display_name: str | None = Field(default=None, alias="templateDisplayName")
    is_assigned: bool | None = Field(default=None, alias="isAssigned")
    role_scope_tag_ids: list[str] | None = Field(default=None, alias="roleScopeTagIds")
    assignments: list[ConfigurationAssignment] | None = None
    settings: list[ConfigurationSetting] | None = None
