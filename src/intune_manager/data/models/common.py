from __future__ import annotations

from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field


class GraphBaseModel(BaseModel):
    """Base class for Graph payload helpers."""

    model_config = ConfigDict(
        populate_by_name=True,
        use_enum_values=True,
        extra="ignore",
        frozen=True,
    )

    @classmethod
    def from_graph(cls, payload: dict[str, Any]) -> Self:
        """Hydrate a model from a raw Graph response."""
        return cls.model_validate(payload)

    def to_graph(self) -> dict[str, Any]:
        """Serialize to a Graph-friendly payload."""
        return self.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
            serialize_as_any=True,
        )


class GraphResource(GraphBaseModel):
    """Shared identifier for Graph resources."""

    id: str = Field(alias="id")


class TimestampedResource(GraphResource):
    """Graph resource including creation/update timestamps."""

    created_date_time: datetime | None = Field(default=None, alias="createdDateTime")
    last_modified_date_time: datetime | None = Field(
        default=None, alias="lastModifiedDateTime"
    )
