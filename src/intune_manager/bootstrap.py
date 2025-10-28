from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from intune_manager.auth import AuthManager

from intune_manager.config import Settings
from intune_manager.data import (
    AuditEventRepository,
    ConfigurationProfileRepository,
    DatabaseManager,
    DeviceRepository,
    GroupRepository,
    MobileAppRepository,
    AssignmentFilterRepository,
)
from intune_manager.data.storage import AttachmentCache
from intune_manager.graph.client import GraphClientConfig, GraphClientFactory
from intune_manager.services import (
    ApplicationService,
    AssignmentFilterService,
    AssignmentImportService,
    AssignmentService,
    AuditLogService,
    ConfigurationService,
    DeviceService,
    DiagnosticsService,
    GroupService,
    ServiceRegistry,
    SyncService,
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


def initialize_domain_services(
    auth_manager: "AuthManager",
    settings: Settings,
) -> ServiceRegistry:
    """Initialize all domain services with configured authentication.

    This should be called after successful authentication configuration.
    Creates GraphClientFactory, repository instances, domain services,
    and the SyncService that coordinates data fetching.

    Args:
        auth_manager: Configured auth manager with valid credentials
        settings: Application settings with tenant configuration

    Returns:
        ServiceRegistry populated with all services including SyncService

    Raises:
        AuthenticationError: If auth_manager is not properly configured
    """
    # Import here to avoid circular dependency
    from intune_manager.auth import AuthManager  # noqa: F401

    logger.info("Initializing domain services with authenticated Graph client")

    # Get existing services from initial bootstrap
    registry = build_services()

    # Create Graph client factory with token provider
    token_provider = auth_manager.token_provider()
    graph_config = GraphClientConfig(
        scopes=list(settings.configured_scopes()),
    )
    client_factory = GraphClientFactory(token_provider, graph_config)

    # Create repository instances
    db = DatabaseManager()
    attachments = AttachmentCache()
    device_repo = DeviceRepository(db)
    app_repo = MobileAppRepository(db)
    group_repo = GroupRepository(db)
    filter_repo = AssignmentFilterRepository(db)
    config_repo = ConfigurationProfileRepository(db)
    audit_repo = AuditEventRepository(db)

    # Create domain services
    devices = DeviceService(client_factory, device_repo)
    applications = ApplicationService(client_factory, app_repo, attachments)
    groups = GroupService(client_factory, group_repo)
    filters = AssignmentFilterService(client_factory, filter_repo)
    configurations = ConfigurationService(client_factory, config_repo)
    audit = AuditLogService(client_factory, audit_repo)
    assignments = AssignmentService(client_factory)

    # Create sync service that coordinates all domain services
    sync = SyncService(
        devices=devices,
        applications=applications,
        groups=groups,
        filters=filters,
        configurations=configurations,
        audit=audit,
    )

    logger.info(
        "Domain services initialized successfully",
        tenant_id=settings.tenant_id,
        service_count=7,
    )

    # Return updated registry with all services
    return ServiceRegistry(
        devices=devices,
        applications=applications,
        groups=groups,
        assignments=assignments,
        assignment_filters=filters,
        configurations=configurations,
        audit=audit,
        sync=sync,
        diagnostics=registry.diagnostics,
        assignment_import=registry.assignment_import,
    )


__all__ = ["build_services", "initialize_domain_services"]
