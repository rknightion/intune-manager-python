from __future__ import annotations

from dataclasses import dataclass

from .applications import ApplicationService
from .assignment_import import AssignmentImportService
from .assignments import AssignmentService
from .audit import AuditLogService
from .configurations import ConfigurationService
from .devices import DeviceService
from .diagnostics import DiagnosticsService
from .export import ExportService
from .filters import AssignmentFilterService
from .groups import GroupService
from .mobile_config import MobileConfigService
from .sync import SyncService


@dataclass(slots=True)
class ServiceRegistry:
    """Centralised container for lazily-initialised services."""

    devices: DeviceService | None = None
    applications: ApplicationService | None = None
    groups: GroupService | None = None
    assignments: AssignmentService | None = None
    assignment_import: AssignmentImportService | None = None
    assignment_filters: AssignmentFilterService | None = None
    configurations: ConfigurationService | None = None
    mobile_config: MobileConfigService | None = None
    audit: AuditLogService | None = None
    export: ExportService | None = None
    sync: SyncService | None = None
    diagnostics: DiagnosticsService | None = None


__all__ = ["ServiceRegistry"]
