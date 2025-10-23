from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Mapping, Sequence
from zipfile import ZIP_DEFLATED, ZipFile

from intune_manager.auth import SecretStore
from intune_manager.config.settings import log_dir
from intune_manager.data import (
    AssignmentFilterRepository,
    AuditEventRepository,
    ConfigurationProfileRepository,
    DatabaseManager,
    DeviceRepository,
    GroupRepository,
    MobileAppRepository,
)
from intune_manager.data.cache_health import (
    CacheHealthReport,
    CacheIntegrityChecker,
)
from intune_manager.data.storage import AttachmentCache, AttachmentMetadata
from intune_manager.utils import get_logger


logger = get_logger(__name__)


@dataclass(slots=True)
class AttachmentStats:
    total_files: int
    total_bytes: int
    last_modified: datetime | None = None


class DiagnosticsService:
    """Provide cache health, attachment, log export, and secret insight helpers."""

    def __init__(
        self,
        db: DatabaseManager,
        attachments: AttachmentCache,
        *,
        secret_store: SecretStore | None = None,
    ) -> None:
        self._db = db
        self._attachments = attachments
        self._secret_store = secret_store or SecretStore()
        self._checker = CacheIntegrityChecker(db)
        self._repositories = self._build_repositories(db)
        self._last_report: CacheHealthReport | None = None

    # --------------------------------------------------------------- Cache Ops

    def inspect_cache(self, *, auto_repair: bool = True) -> CacheHealthReport:
        report = self._checker.inspect(auto_repair=auto_repair)
        self._last_report = report
        logger.info(
            "Cache integrity inspection completed",
            severity=report.severity.value,
            issues=len(report.issues),
        )
        return report

    def clear_cache(self, resource: str, *, tenant_id: str | None = None) -> None:
        repository = self._repositories.get(resource)
        if repository is None:
            raise ValueError(f"Unknown cache resource: {resource}")
        repository.clear(tenant_id=tenant_id)
        logger.info("Cleared cache", resource=resource, tenant_id=tenant_id)

    def clear_all_caches(self, *, tenant_id: str | None = None) -> None:
        for name in self._repositories:
            self.clear_cache(name, tenant_id=tenant_id)

    def cache_resources(self) -> Sequence[str]:
        return tuple(self._repositories.keys())

    def last_cache_report(self) -> CacheHealthReport | None:
        return self._last_report

    # ----------------------------------------------------------- Attachments

    def purge_attachments(self, *, tenant_id: str | None = None) -> None:
        self._attachments.purge(tenant_id=tenant_id)
        logger.info("Purged attachment cache", tenant_id=tenant_id)

    def attachment_stats(self, *, tenant_id: str | None = None) -> AttachmentStats:
        total_bytes = 0
        total_files = 0
        last_modified: datetime | None = None
        for metadata in self._enumerate_attachments(tenant_id=tenant_id):
            total_files += 1
            total_bytes += metadata.size_bytes
            if last_modified is None or metadata.last_accessed > last_modified:
                last_modified = metadata.last_accessed
        return AttachmentStats(
            total_files=total_files,
            total_bytes=total_bytes,
            last_modified=last_modified,
        )

    def _enumerate_attachments(
        self,
        *,
        tenant_id: str | None = None,
    ) -> Iterable[AttachmentMetadata]:
        root = self._attachments.base_dir(tenant_id=tenant_id)
        if not root.exists():
            return []
        for path in sorted(root.rglob("*")):
            if path.is_file():
                stat = path.stat()
                yield AttachmentMetadata(
                    key=path.stem,
                    path=path,
                    size_bytes=stat.st_size,
                    last_accessed=datetime.fromtimestamp(stat.st_atime),
                    tenant_id=tenant_id,
                )

    # ------------------------------------------------------------- Logging

    def log_files(self) -> Sequence[Path]:
        directory = log_dir()
        return tuple(sorted(directory.glob("*.log*")))

    def export_logs(self, target: Path) -> Path:
        if target.is_dir():
            timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
            target = target / f"intune-manager-logs-{timestamp}.zip"
        target.parent.mkdir(parents=True, exist_ok=True)
        files = self.log_files()
        if not files:
            raise FileNotFoundError("No log files available to export.")
        with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
            for file in files:
                archive.write(file, arcname=file.name)
        logger.info("Exported log bundle", destination=str(target), files=len(files))
        return target

    # -------------------------------------------------------- Secret insight

    def secret_presence(self, keys: Mapping[str, str] | None = None) -> Dict[str, bool]:
        target_keys = keys or {"client_secret": "MSAL client secret"}
        return {
            label: self._secret_store.get_secret(key) is not None
            for key, label in target_keys.items()
        }

    # ------------------------------------------------------------- Internals

    def _build_repositories(self, db: DatabaseManager) -> Dict[str, object]:
        return {
            "devices": DeviceRepository(db),
            "mobile_apps": MobileAppRepository(db),
            "groups": GroupRepository(db),
            "configuration_profiles": ConfigurationProfileRepository(db),
            "audit_events": AuditEventRepository(db),
            "assignment_filters": AssignmentFilterRepository(db),
        }


__all__ = ["DiagnosticsService", "AttachmentStats"]
