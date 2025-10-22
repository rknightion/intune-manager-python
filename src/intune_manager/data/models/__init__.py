"""Domain models representing Microsoft Graph Intune resources."""

from .application import MobileApp
from .assignment import (
    AllDevicesAssignmentTarget,
    AssignmentIntent,
    AssignmentSettings,
    AssignmentTarget,
    FilteredGroupAssignmentTarget,
    GroupAssignmentTarget,
    MobileAppAssignment,
)
from .audit import AuditEvent
from .common import GraphBaseModel, GraphResource, TimestampedResource
from .configuration import ConfigurationProfile, ConfigurationSetting, SettingTemplate
from .device import InstalledApp, ManagedDevice
from .filters import AssignmentFilter
from .group import DirectoryGroup, GroupMember

__all__ = [
    "GraphBaseModel",
    "GraphResource",
    "TimestampedResource",
    "ManagedDevice",
    "InstalledApp",
    "MobileApp",
    "AssignmentTarget",
    "GroupAssignmentTarget",
    "AllDevicesAssignmentTarget",
    "FilteredGroupAssignmentTarget",
    "AssignmentSettings",
    "AssignmentIntent",
    "MobileAppAssignment",
    "DirectoryGroup",
    "GroupMember",
    "AssignmentFilter",
    "ConfigurationProfile",
    "ConfigurationSetting",
    "SettingTemplate",
    "AuditEvent",
]
