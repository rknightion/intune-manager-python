from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from pydantic import ValidationError

from intune_manager.data import (
    AssignmentIntent,
    AssignmentSettings,
    DirectoryGroup,
    MobileApp,
    MobileAppAssignment,
)
from intune_manager.data.models.assignment import GroupAssignmentTarget
from intune_manager.utils import CancellationToken, ProgressCallback, ProgressTracker, get_logger


logger = get_logger(__name__)

@dataclass(slots=True)
class AssignmentImportRowResult:
    """Status for a single CSV row during import parsing."""

    row_number: int
    app_name: str
    group_name: str
    intent_raw: str | None
    settings_raw: str | None
    resolved_app_id: str | None = None
    resolved_group_id: str | None = None
    assignment: MobileAppAssignment | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def status_label(self) -> str:
        if self.errors:
            return "Error"
        if self.warnings:
            return "Warning"
        return "OK"


@dataclass(slots=True)
class AssignmentImportResult:
    """Aggregated outcome for a parsed CSV file."""

    rows: list[AssignmentImportRowResult]
    assignments_by_app: dict[str, list[MobileAppAssignment]]
    warnings: list[str]
    errors: list[str]

    def has_fatal_errors(self) -> bool:
        return bool(self.errors)


class AssignmentImportError(Exception):
    """Raised when an import file cannot be processed."""

class AssignmentImportService:
    """Parse CSV-based assignment imports into validated MobileAppAssignment payloads."""

    REQUIRED_COLUMNS = ("AppName", "GroupName", "Intent")
    OPTIONAL_COLUMNS = ("Settings",)

    def parse_csv(
        self,
        path: Path,
        *,
        apps: Iterable[MobileApp],
        groups: Iterable[DirectoryGroup],
        progress: ProgressCallback | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> AssignmentImportResult:
        if not path.exists():
            raise AssignmentImportError(f"File not found: {path}")

        if cancellation_token:
            cancellation_token.raise_if_cancelled()

        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise AssignmentImportError("CSV file is missing a header row.")

            missing_columns = [
                column for column in self.REQUIRED_COLUMNS if column not in reader.fieldnames
            ]
            if missing_columns:
                raise AssignmentImportError(
                    f"CSV missing required column(s): {', '.join(missing_columns)}",
                )

            rows = list(reader)

        total_rows = len(rows)
        app_index = self._build_app_index(apps)
        group_index = self._build_group_index(groups)

        results: list[AssignmentImportRowResult] = []
        assignments: dict[str, list[MobileAppAssignment]] = {}
        aggregated_warnings: list[str] = []
        aggregated_errors: list[str] = []
        tracker = ProgressTracker(progress) if progress else None
        if tracker:
            tracker.start(total=total_rows, current="Preparing assignment import…")

        if total_rows == 0:
            if cancellation_token:
                cancellation_token.raise_if_cancelled()
            return AssignmentImportResult(
                rows=[],
                assignments_by_app={},
                warnings=["Import file contained no data rows."],
                errors=[],
            )

        for offset, row in enumerate(rows, start=2):
            if cancellation_token:
                cancellation_token.raise_if_cancelled()
            if tracker:
                tracker.step(current=f"Parsing row {offset}")
            result = self._parse_row(row, offset, app_index, group_index)
            results.append(result)

            if result.errors:
                if tracker:
                    tracker.failed(current=f"Row {result.row_number} failed validation")
                aggregated_errors.extend(f"Row {result.row_number}: {error}" for error in result.errors)
                continue
            if result.warnings:
                aggregated_warnings.extend(
                    f"Row {result.row_number}: {warning}" for warning in result.warnings
                )
            if tracker:
                tracker.succeeded(current=f"Row {result.row_number} processed")
            if result.assignment is not None and result.resolved_app_id is not None:
                assignments.setdefault(result.resolved_app_id, []).append(result.assignment)

        if tracker:
            tracker.finish()
        if cancellation_token:
            cancellation_token.raise_if_cancelled()

        return AssignmentImportResult(
            rows=results,
            assignments_by_app=assignments,
            warnings=aggregated_warnings,
            errors=aggregated_errors,
        )

    # ------------------------------------------------------------------ Helpers

    def _parse_row(
        self,
        row: dict[str, str],
        row_number: int,
        app_index: dict[str, MobileApp],
        group_index: dict[str, DirectoryGroup],
    ) -> AssignmentImportRowResult:
        app_name = (row.get("AppName") or "").strip()
        group_name = (row.get("GroupName") or "").strip()
        intent_raw = (row.get("Intent") or "").strip()
        settings_raw = (row.get("Settings") or "").strip()

        result = AssignmentImportRowResult(
            row_number=row_number,
            app_name=app_name,
            group_name=group_name,
            intent_raw=intent_raw or None,
            settings_raw=settings_raw or None,
        )

        if not app_name:
            result.errors.append("Missing AppName value.")
            return result
        if not group_name:
            result.errors.append("Missing GroupName value.")
            return result
        if not intent_raw:
            result.errors.append("Missing Intent value.")
            return result

        app = app_index.get(app_name.lower())
        if app is None or not app.id:
            result.errors.append(f"Application '{app_name}' not found in cache.")
            return result

        group = group_index.get(group_name.lower())
        if group is None or not group.id:
            result.errors.append(f"Group '{group_name}' not found in cache.")
            return result

        try:
            intent = self._resolve_intent(intent_raw)
        except ValueError as exc:
            result.errors.append(str(exc))
            return result

        settings_obj: AssignmentSettings | None = None
        if settings_raw:
            try:
                parsed = json.loads(settings_raw)
                if not isinstance(parsed, dict):
                    raise ValueError("Settings must be a JSON object.")
                settings_obj = AssignmentSettings.model_validate(parsed)
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                result.errors.append(f"Invalid Settings payload: {exc}")
                return result

        target = GroupAssignmentTarget(group_id=group.id)
        assignment = MobileAppAssignment.model_construct(
            id=None,
            intent=intent,
            target=target,
            settings=settings_obj,
        )

        result.assignment = assignment
        result.resolved_app_id = app.id
        result.resolved_group_id = group.id

        if app.platform_type is None:
            result.warnings.append("App platform unknown; review compatibility after import.")
        elif intent is AssignmentIntent.AVAILABLE_WITHOUT_ENROLLMENT and app.platform_type not in {
            "ios",
            "iosVpp",
        }:
            result.warnings.append(
                f"Intent '{intent.value}' typically targets iOS apps; review platform '{app.platform_type}'.",
            )

        return result

    def _resolve_intent(self, value: str) -> AssignmentIntent:
        normalised = value.strip().lower().replace(" ", "").replace("-", "").replace("_", "")

        for intent in AssignmentIntent:
            token = intent.value.lower().replace(" ", "").replace("-", "")
            if normalised == token:
                return intent

        raise ValueError(f"Unknown assignment intent '{value}'.")

    def _build_app_index(self, apps: Iterable[MobileApp]) -> dict[str, MobileApp]:
        index: dict[str, MobileApp] = {}
        for app in apps:
            if not app.display_name:
                continue
            key = app.display_name.strip().lower()
            if key in index:
                logger.warning(
                    "Duplicate application display name encountered during import index build",
                    app_name=app.display_name,
                    existing=index[key].id,
                    duplicate=app.id,
                )
                # Keep first occurrence; later duplicates require explicit disambiguation.
                continue
            index[key] = app
        return index

    def _build_group_index(self, groups: Iterable[DirectoryGroup]) -> dict[str, DirectoryGroup]:
        index: dict[str, DirectoryGroup] = {}
        for group in groups:
            if not group.display_name:
                continue
            key = group.display_name.strip().lower()
            if key in index:
                logger.warning(
                    "Duplicate group display name encountered during import index build",
                    group_name=group.display_name,
                    existing=index[key].id,
                    duplicate=group.id,
                )
                continue
            index[key] = group
        return index

__all__ = [
    "AssignmentImportError",
    "AssignmentImportResult",
    "AssignmentImportRowResult",
    "AssignmentImportService",
]
