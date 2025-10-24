from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import ConfigDict, Field

from .common import GraphBaseModel, GraphResource


class AssignmentIntent(StrEnum):
    REQUIRED = "required"
    AVAILABLE = "available"
    UNINSTALL = "uninstall"
    AVAILABLE_WITHOUT_ENROLLMENT = "availableWithoutEnrollment"
    UNKNOWN = "unknown"


class AssignmentTarget(GraphBaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        use_enum_values=True,
        extra="ignore",
        frozen=True,
    )

    odata_type: str = Field(alias="@odata.type")


class GroupAssignmentTarget(AssignmentTarget):
    odata_type: Literal["#microsoft.graph.groupAssignmentTarget"] = Field(
        default="#microsoft.graph.groupAssignmentTarget",
        alias="@odata.type",
    )
    group_id: str = Field(alias="groupId")


class AllDevicesAssignmentTarget(AssignmentTarget):
    odata_type: Literal["#microsoft.graph.allDevicesAssignmentTarget"] = Field(
        default="#microsoft.graph.allDevicesAssignmentTarget",
        alias="@odata.type",
    )


class FilteredGroupAssignmentTarget(AssignmentTarget):
    odata_type: Literal["#microsoft.graph.exclusionGroupAssignmentTarget"] = Field(
        default="#microsoft.graph.exclusionGroupAssignmentTarget",
        alias="@odata.type",
    )
    group_id: str = Field(alias="groupId")
    assignment_filter_id: str | None = Field(
        default=None,
        alias="assignmentFilterId",
    )


class AssignmentSettings(GraphBaseModel):
    """Placeholder for strongly typed assignment settings."""

    odata_type: str | None = Field(default=None, alias="@odata.type")
    start_date_time: datetime | None = Field(default=None, alias="startDateTime")
    deadline_date_time: datetime | None = Field(default=None, alias="deadlineDateTime")


class MobileAppAssignment(GraphResource):
    intent: AssignmentIntent
    target: AssignmentTarget
    settings: AssignmentSettings | None = None
