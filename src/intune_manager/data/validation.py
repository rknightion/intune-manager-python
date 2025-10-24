from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, List, Type, TypeVar

from pydantic import ValidationError

from intune_manager.data.models import GraphBaseModel
from intune_manager.utils import get_logger


logger = get_logger(__name__)

ModelT = TypeVar("ModelT", bound=GraphBaseModel)


@dataclass(slots=True)
class ValidationIssue:
    """Represents a schema validation failure for a Graph payload."""

    resource: str
    identifier: str | None
    message: str
    detail: str | None = None
    fields: tuple[str, ...] = field(default_factory=tuple)


class GraphResponseValidator:
    """Validate Microsoft Graph payloads against expected schemas."""

    def __init__(
        self,
        resource: str,
        *,
        issue_callback: Callable[[ValidationIssue], None] | None = None,
    ) -> None:
        self._resource = resource
        self._issue_callback = issue_callback
        self._issues: list[ValidationIssue] = []

    # ------------------------------------------------------------------ Public

    def parse(
        self,
        model: Type[ModelT],
        payload: dict[str, Any],
    ) -> ModelT | None:
        """Validate and parse a single Graph payload."""

        try:
            return model.from_graph(payload)
        except ValidationError as exc:
            issue = self._build_issue(payload, exc)
            self._record_issue(issue, exc)
            return None

    def parse_many(
        self,
        model: Type[ModelT],
        payloads: Iterable[dict[str, Any]],
    ) -> list[ModelT]:
        """Validate and parse an iterable, skipping invalid payloads."""

        items: list[ModelT] = []
        for payload in payloads:
            item = self.parse(model, payload)
            if item is not None:
                items.append(item)
        return items

    def issues(self) -> list[ValidationIssue]:
        return list(self._issues)

    def reset(self) -> None:
        self._issues.clear()

    # ----------------------------------------------------------------- Helpers

    def _build_issue(
        self,
        payload: dict[str, Any],
        exc: ValidationError,
    ) -> ValidationIssue:
        identifier = None
        if isinstance(payload, dict):
            raw_id = payload.get("id")
            identifier = str(raw_id) if raw_id is not None else None
        fields = tuple(
            ".".join(str(segment) for segment in error.get("loc", ()))
            for error in exc.errors()
        )
        detail = exc.json()
        return ValidationIssue(
            resource=self._resource,
            identifier=identifier,
            message="Graph payload failed schema validation",
            detail=detail,
            fields=fields,
        )

    def _record_issue(self, issue: ValidationIssue, exc: ValidationError) -> None:
        self._issues.append(issue)
        field_list = ", ".join(issue.fields) if issue.fields else "unknown"
        logger.warning(
            "Graph payload validation failed",
            resource=self._resource,
            identifier=issue.identifier,
            fields=field_list,
            errors=exc.errors(),
        )
        if self._issue_callback is not None:
            try:
                self._issue_callback(issue)
            except (
                Exception
            ):  # pragma: no cover - callbacks should not break validation
                logger.exception("Validation issue callback raised an exception")


__all__: List[str] = ["GraphResponseValidator", "ValidationIssue"]
