from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, Iterable, List, Sequence, Tuple

from pydantic import ValidationError
from sqlalchemy import select
from sqlmodel import SQLModel, Session

from intune_manager.data.repositories.base import DEFAULT_SCOPE
from intune_manager.data.sql import CacheEntry, DatabaseManager
from intune_manager.data.sql.mapper import (
    record_to_assignment_filter,
    record_to_audit_event,
    record_to_configuration,
    record_to_device,
    record_to_group,
    record_to_mobile_app,
)
from intune_manager.data.sql.models import (
    AssignmentFilterRecord,
    AuditEventRecord,
    ConfigurationProfileRecord,
    DeviceRecord,
    GroupRecord,
    MobileAppRecord,
)
from intune_manager.utils import get_logger


logger = get_logger(__name__)


class CacheIssueSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(slots=True)
class CacheIssue:
    """Describes a cache validation finding."""

    resource: str
    scope: str
    message: str
    severity: CacheIssueSeverity
    detail: str | None = None


@dataclass(slots=True)
class CacheEntryStatus:
    """Represents health metadata for a cache entry."""

    resource: str
    scope: str
    tenant_id: str | None
    recorded_count: int | None
    actual_count: int
    last_refresh: datetime | None = None
    expires_at: datetime | None = None
    repaired: bool = False
    issues: tuple[CacheIssue, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class CacheHealthReport:
    """Aggregate report for cache integrity checks."""

    generated_at: datetime
    entries: tuple[CacheEntryStatus, ...]
    issues: tuple[CacheIssue, ...]

    @property
    def severity(self) -> CacheIssueSeverity:
        highest = CacheIssueSeverity.INFO
        for issue in self.issues:
            if issue.severity == CacheIssueSeverity.ERROR:
                return CacheIssueSeverity.ERROR
            if issue.severity == CacheIssueSeverity.WARNING:
                highest = CacheIssueSeverity.WARNING
        return highest


@dataclass(slots=True)
class ResourceDescriptor:
    """Metadata describing how to inspect a cached resource."""

    name: str
    record_model: type[SQLModel]
    converter: Callable[[SQLModel], object]

    @property
    def has_tenant_column(self) -> bool:
        return hasattr(self.record_model, "tenant_id")


RESOURCE_REGISTRY: Tuple[ResourceDescriptor, ...] = (
    ResourceDescriptor("devices", DeviceRecord, record_to_device),
    ResourceDescriptor("mobile_apps", MobileAppRecord, record_to_mobile_app),
    ResourceDescriptor("groups", GroupRecord, record_to_group),
    ResourceDescriptor(
        "configuration_profiles", ConfigurationProfileRecord, record_to_configuration
    ),
    ResourceDescriptor("audit_events", AuditEventRecord, record_to_audit_event),
    ResourceDescriptor(
        "assignment_filters", AssignmentFilterRecord, record_to_assignment_filter
    ),
)


class CacheIntegrityChecker:
    """Inspect cached SQLModel tables for consistency issues."""

    def __init__(
        self,
        db: DatabaseManager,
        *,
        resources: Sequence[ResourceDescriptor] = RESOURCE_REGISTRY,
    ) -> None:
        self._db = db
        self._resources = resources

    # ------------------------------------------------------------------ Public

    def inspect(self, *, auto_repair: bool = True) -> CacheHealthReport:
        """Run integrity checks across all registered resources."""

        issues: list[CacheIssue] = []
        entry_statuses: list[CacheEntryStatus] = []
        now = datetime.utcnow()

        with self._db.session() as session:
            entry_map = self._load_cache_entries(session)
            processed_keys: set[tuple[str, str]] = set()

            for descriptor in self._resources:
                scopes = self._collect_scopes(session, entry_map, descriptor)
                for tenant_id in scopes:
                    scope_key = self._scope_key(tenant_id)
                    entry = entry_map.get((descriptor.name, scope_key))
                    status, scope_issues = self._inspect_scope(
                        session,
                        descriptor,
                        tenant_id,
                        entry,
                        auto_repair=auto_repair,
                    )
                    if scope_issues:
                        issues.extend(scope_issues)
                    if status is not None:
                        entry_statuses.append(status)
                        processed_keys.add((descriptor.name, scope_key))

            # Handle cache entries that refer to unknown resources or empty tables
            for (resource, scope), entry in entry_map.items():
                if (resource, scope) in processed_keys:
                    continue
                issue = CacheIssue(
                    resource=resource,
                    scope=scope,
                    message="Cache entry references unknown resource.",
                    severity=CacheIssueSeverity.WARNING,
                )
                issues.append(issue)
                logger.warning(
                    "Removing cache entry for unknown resource",
                    resource=resource,
                    scope=scope,
                )
                if auto_repair:
                    session.delete(entry)
                entry_statuses.append(
                    CacheEntryStatus(
                        resource=resource,
                        scope=scope,
                        tenant_id=entry.tenant_id,
                        recorded_count=entry.item_count,
                        actual_count=0,
                        repaired=auto_repair,
                        issues=(issue,),
                    ),
                )

            if auto_repair:
                session.commit()

        report = CacheHealthReport(
            generated_at=now,
            entries=tuple(entry_statuses),
            issues=tuple(issues),
        )
        return report

    # ----------------------------------------------------------------- Helpers

    def _load_cache_entries(
        self, session: Session
    ) -> Dict[tuple[str, str], CacheEntry]:
        entries = session.exec(select(CacheEntry)).all()
        return {(entry.resource, entry.scope): entry for entry in entries}

    def _collect_scopes(
        self,
        session: Session,
        entry_map: Dict[tuple[str, str], CacheEntry],
        descriptor: ResourceDescriptor,
    ) -> Iterable[str | None]:
        tenants: set[str | None] = set()
        if descriptor.has_tenant_column:
            rows = session.exec(
                select(descriptor.record_model.tenant_id).distinct(),
            ).all()
            tenants.update(row for row in rows)
        else:
            tenants.add(None)

        for (resource, _scope), entry in entry_map.items():
            if resource == descriptor.name:
                tenants.add(entry.tenant_id)
        return tenants

    def _inspect_scope(
        self,
        session: Session,
        descriptor: ResourceDescriptor,
        tenant_id: str | None,
        entry: CacheEntry | None,
        *,
        auto_repair: bool,
    ) -> tuple[CacheEntryStatus | None, tuple[CacheIssue, ...]]:
        issues: list[CacheIssue] = []
        scope = self._scope_key(tenant_id)
        rows = self._load_records(session, descriptor, tenant_id)

        actual_count = 0
        repaired = False
        for record in rows:
            try:
                descriptor.converter(record)
                actual_count += 1
            except ValidationError as exc:
                issue = CacheIssue(
                    resource=descriptor.name,
                    scope=scope,
                    message="Cached payload failed model validation; purging entry.",
                    severity=CacheIssueSeverity.ERROR,
                    detail=str(exc.errors()),
                )
                issues.append(issue)
                logger.error(
                    "Purging invalid cached record",
                    resource=descriptor.name,
                    scope=scope,
                    errors=exc.errors(),
                )
                if auto_repair:
                    session.delete(record)
                    repaired = True

        if entry is None:
            if actual_count == 0:
                return None, tuple(issues)
            issue = CacheIssue(
                resource=descriptor.name,
                scope=scope,
                message="Discovered cached records without metadata entry.",
                severity=CacheIssueSeverity.WARNING,
            )
            issues.append(issue)
            logger.warning(
                "Discovered orphaned cache records",
                resource=descriptor.name,
                scope=scope,
                count=actual_count,
            )
            if auto_repair:
                entry = CacheEntry(
                    resource=descriptor.name,
                    scope=scope,
                    tenant_id=tenant_id,
                    item_count=actual_count,
                    last_refresh=None,
                    expires_at=None,
                )
                session.add(entry)
                repaired = True
                recorded_count = 0
            else:
                recorded_count = None
        else:
            recorded_count = entry.item_count
            last_refresh = entry.last_refresh
            expires_at = entry.expires_at
            if (recorded_count or 0) != actual_count:
                issue = CacheIssue(
                    resource=descriptor.name,
                    scope=scope,
                    message=(
                        "Cached record count does not match metadata; "
                        "normalising entry."
                    ),
                    severity=CacheIssueSeverity.WARNING,
                )
                issues.append(issue)
                logger.warning(
                    "Normalising cache entry count",
                    resource=descriptor.name,
                    scope=scope,
                    recorded=recorded_count,
                    actual=actual_count,
                )
                if auto_repair:
                    entry.item_count = actual_count
                    repaired = True

        if entry is None:
            last_refresh = None
            expires_at = None

        status = CacheEntryStatus(
            resource=descriptor.name,
            scope=scope,
            tenant_id=tenant_id,
            recorded_count=recorded_count,
            actual_count=actual_count,
            last_refresh=last_refresh,
            expires_at=expires_at,
            repaired=repaired,
            issues=tuple(issues),
        )
        return status, tuple(issues)

    def _load_records(
        self,
        session: Session,
        descriptor: ResourceDescriptor,
        tenant_id: str | None,
    ) -> Iterable[SQLModel]:
        stmt = select(descriptor.record_model)
        if descriptor.has_tenant_column:
            stmt = stmt.where(descriptor.record_model.tenant_id == tenant_id)
        return session.exec(stmt).all()

    def _scope_key(self, tenant_id: str | None) -> str:
        return tenant_id or DEFAULT_SCOPE


__all__: List[str] = [
    "CacheHealthReport",
    "CacheIntegrityChecker",
    "CacheIssue",
    "CacheIssueSeverity",
    "CacheEntryStatus",
]
