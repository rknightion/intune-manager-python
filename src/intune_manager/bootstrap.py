from __future__ import annotations

from intune_manager.data import DatabaseManager
from intune_manager.data.storage import AttachmentCache
from intune_manager.services import (
    AssignmentImportService,
    DiagnosticsService,
    ServiceRegistry,
)
from intune_manager.utils import get_logger, safe_mode_enabled


logger = get_logger(__name__)


def build_services() -> ServiceRegistry:
    """Initialise core service dependencies for the UI shell."""

    db = DatabaseManager()
    db.ensure_schema()
    attachments = AttachmentCache()
    diagnostics = DiagnosticsService(db, attachments)
    if safe_mode_enabled():
        logger.warning("Safe mode active; skipping cache integrity inspection")
    else:
        try:
            diagnostics.inspect_cache(auto_repair=True)
        except Exception:  # noqa: BLE001 - diagnostics should not block startup
            logger.exception("Cache integrity inspection failed during startup")
    logger.debug("Service registry initialised with diagnostics service")
    assignment_import = AssignmentImportService()
    return ServiceRegistry(
        diagnostics=diagnostics,
        assignment_import=assignment_import,
    )


__all__ = ["build_services"]
