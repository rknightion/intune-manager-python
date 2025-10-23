from __future__ import annotations

from intune_manager.data import DatabaseManager
from intune_manager.data.storage import AttachmentCache
from intune_manager.services import DiagnosticsService, ServiceRegistry
from intune_manager.utils import get_logger


logger = get_logger(__name__)


def build_services() -> ServiceRegistry:
    """Initialise core service dependencies for the UI shell."""

    db = DatabaseManager()
    db.ensure_schema()
    attachments = AttachmentCache()
    diagnostics = DiagnosticsService(db, attachments)
    logger.debug("Service registry initialised with diagnostics service")
    return ServiceRegistry(
        diagnostics=diagnostics,
    )


__all__ = ["build_services"]
