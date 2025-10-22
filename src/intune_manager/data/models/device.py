from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field

from .common import GraphResource


class ComplianceState(StrEnum):
    UNKNOWN = "unknown"
    COMPLIANT = "compliant"
    NONCOMPLIANT = "noncompliant"
    CONFLICT = "conflict"
    ERROR = "error"
    IN_GRACE_PERIOD = "inGracePeriod"
    CONFIG_MANAGER = "configManager"


class ManagementState(StrEnum):
    MANAGED = "managed"
    RETIRE_PENDING = "retirePending"
    RETIRE_FAILED = "retireFailed"
    WIPE_PENDING = "wipePending"
    WIPE_FAILED = "wipeFailed"
    UNHEALTHY = "unhealthy"
    DELETE_PENDING = "deletePending"
    RETIRE_ISSUED = "retireIssued"
    WIPE_ISSUED = "wipeIssued"
    WIPE_CANCELED = "wipeCanceled"
    RETIRE_CANCELED = "retireCanceled"
    DISCOVERED = "discovered"


class Ownership(StrEnum):
    UNKNOWN = "unknown"
    COMPANY = "company"
    PERSONAL = "personal"
    SHARED = "shared"


class InstalledApp(GraphResource):
    display_name: str | None = Field(default=None, alias="displayName")
    version: str | None = None
    publisher: str | None = None
    size_in_bytes: int | None = Field(default=None, alias="sizeInBytes")
    install_state: str | None = Field(default=None, alias="installState")
    last_sync_date_time: datetime | None = Field(default=None, alias="lastSyncDateTime")


class ManagedDevice(GraphResource):
    device_name: str = Field(alias="deviceName")
    model: str | None = None
    manufacturer: str | None = None
    operating_system: str = Field(alias="operatingSystem")
    os_version: str | None = Field(default=None, alias="osVersion")
    user_display_name: str | None = Field(default=None, alias="userDisplayName")
    user_principal_name: str | None = Field(default=None, alias="userPrincipalName")
    user_id: str | None = Field(default=None, alias="userId")
    email_address: str | None = Field(default=None, alias="emailAddress")
    azure_ad_device_id: str | None = Field(default=None, alias="azureADDeviceId")
    azure_ad_registered: bool | None = Field(default=None, alias="azureADRegistered")
    compliance_state: ComplianceState | None = Field(
        default=None, alias="complianceState"
    )
    management_state: ManagementState | None = Field(
        default=None, alias="managementState"
    )
    ownership: Ownership | None = None
    serial_number: str | None = Field(default=None, alias="serialNumber")
    imei: str | None = None
    meid: str | None = None
    udid: str | None = None
    ethernet_mac_address: str | None = Field(default=None, alias="ethernetMacAddress")
    wi_fi_mac_address: str | None = Field(default=None, alias="wiFiMacAddress")
    ip_address_v4: str | None = Field(default=None, alias="ipAddressV4")
    enrolled_date_time: datetime | None = Field(default=None, alias="enrolledDateTime")
    last_sync_date_time: datetime | None = Field(default=None, alias="lastSyncDateTime")
    compliance_grace_period_expiration_date_time: datetime | None = Field(
        default=None,
        alias="complianceGracePeriodExpirationDateTime",
    )
    managed_device_name: str | None = Field(default=None, alias="managedDeviceName")
    device_category_display_name: str | None = Field(
        default=None, alias="deviceCategoryDisplayName"
    )
    is_encrypted: bool | None = Field(default=None, alias="isEncrypted")
    is_supervised: bool | None = Field(default=None, alias="isSupervised")
    jailbreak_detection_state: str | None = Field(default=None, alias="jailBroken")
    enrolled_by_user: str | None = Field(default=None, alias="enrolledByUser")
    device_registration_state: str | None = Field(
        default=None, alias="deviceRegistrationState"
    )
    exchange_access_state: str | None = Field(default=None, alias="exchangeAccessState")
    exchange_last_successful_sync_date_time: datetime | None = Field(
        default=None,
        alias="exchangeLastSuccessfulSyncDateTime",
    )
    lost_mode_state: str | None = Field(default=None, alias="lostModeState")
    chassis_type: str | None = Field(default=None, alias="chassisType")
    sku_family: str | None = Field(default=None, alias="skuFamily")
    sku_number: int | None = Field(default=None, alias="skuNumber")
    total_storage_space_in_bytes: int | None = Field(
        default=None, alias="totalStorageSpaceInBytes"
    )
    free_storage_space_in_bytes: int | None = Field(
        default=None, alias="freeStorageSpaceInBytes"
    )
    physical_memory_in_bytes: int | None = Field(
        default=None, alias="physicalMemoryInBytes"
    )
    battery_health_percentage: int | None = Field(
        default=None, alias="batteryHealthPercentage"
    )
    battery_level_percentage: float | None = Field(
        default=None, alias="batteryLevelPercentage"
    )
    partner_reported_threat_state: str | None = Field(
        default=None, alias="partnerReportedThreatState"
    )
    bootstrap_token_escrowed: bool | None = Field(
        default=None, alias="bootstrapTokenEscrowed"
    )
    device_firmware_configuration_interface_managed: bool | None = Field(
        default=None,
        alias="deviceFirmwareConfigurationInterfaceManaged",
    )

    # Relationships
    installed_apps: list[InstalledApp] | None = Field(
        default=None, alias="installedApps"
    )
    enrolled_managed_by: (
        Literal["companyPortal", "appleConfigurator", "unknown"] | None
    ) = Field(
        default=None,
        alias="enrollmentType",
    )
