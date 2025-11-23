"""Domain models representing Microsoft Graph Intune resources."""

from .application import MobileApp, MobileAppPlatform
from .assignment import (
    AllDevicesAssignmentTarget,
    AssignmentFilterType,
    AssignmentIntent,
    AssignmentSettings,
    AssignmentTarget,
    FilteredGroupAssignmentTarget,
    GroupAssignmentTarget,
    MobileAppAssignment,
)
from .audit import AuditEvent
from .common import GraphBaseModel, GraphResource, TimestampedResource
from .configuration import (
    ConfigurationPlatform,
    ConfigurationProfile,
    ConfigurationSetting,
    SettingTemplate,
)
from .device import (
    ComplianceState,
    InstalledApp,
    ManagedDevice,
    ManagementState,
    Ownership,
)
from .filters import AssignmentFilter, AssignmentFilterPlatform
from .group import DirectoryGroup, GroupMember

__all__ = [
    "GraphBaseModel",
    "GraphResource",
    "TimestampedResource",
    "ManagedDevice",
    "InstalledApp",
    "ComplianceState",
    "ManagementState",
    "Ownership",
    "MobileApp",
    "MobileAppPlatform",
    "AssignmentTarget",
    "GroupAssignmentTarget",
    "AllDevicesAssignmentTarget",
    "FilteredGroupAssignmentTarget",
    "AssignmentSettings",
    "AssignmentIntent",
    "AssignmentFilterType",
    "MobileAppAssignment",
    "DirectoryGroup",
    "GroupMember",
    "AssignmentFilter",
    "AssignmentFilterPlatform",
    "ConfigurationProfile",
    "ConfigurationPlatform",
    "ConfigurationSetting",
    "SettingTemplate",
    "AuditEvent",
]
