from __future__ import annotations

import io
import json
import platform
import tarfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence
from zipfile import ZIP_DEFLATED, ZipFile

from importlib.metadata import PackageNotFoundError, version

from intune_manager.auth import SecretStore
from intune_manager.config.settings import SettingsManager, config_dir, log_dir
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
                    last_accessed=datetime.fromtimestamp(stat.st_atime, tz=UTC),
                    tenant_id=tenant_id,
                )

    # ------------------------------------------------------------- Logging

    def log_files(self) -> Sequence[Path]:
        directory = log_dir()
        return tuple(sorted(directory.glob("*.log*")))

    def export_logs(self, target: Path) -> Path:
        if target.is_dir():
            timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
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

    def create_diagnostic_bundle(
        self,
        target: Path | None = None,
        *,
        tenant_id: str | None = None,
    ) -> Path:
        """Generate a compressed diagnostic bundle with logs and state metadata."""

        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        bundle_path = self._resolve_bundle_path(target, timestamp)
        bundle_path.parent.mkdir(parents=True, exist_ok=True)

        cache_report = self._checker.inspect(auto_repair=False)
        attachment_stats = self.attachment_stats(tenant_id=tenant_id)
        log_files = list(self.log_files())
        crash_reports = list(self._crash_reports())
        metadata = self._build_metadata(timestamp, tenant_id=tenant_id)
        cache_summary = self._cache_summary(tenant_id=tenant_id)
        settings_snapshot = self._settings_snapshot()

        with tarfile.open(bundle_path, "w:xz") as archive:
            self._add_json(
                archive,
                "metadata.json",
                metadata,
            )
            self._add_json(
                archive,
                "cache/health.json",
                self._serialize_cache_report(cache_report),
            )
            self._add_json(
                archive,
                "cache/summary.json",
                cache_summary,
            )
            self._add_json(
                archive,
                "attachments/stats.json",
                self._serialize_attachment_stats(attachment_stats, tenant_id),
            )
            self._add_json(
                archive,
                "config/settings.json",
                settings_snapshot,
            )

            for path in log_files:
                archive.add(path, arcname=f"logs/{path.name}")
            for path in crash_reports:
                archive.add(path, arcname=f"logs/{path.name}")

        logger.info(
            "Diagnostic bundle created",
            destination=str(bundle_path),
            logs=len(log_files),
            crashes=len(crash_reports),
        )
        return bundle_path

    # -------------------------------------------------------- Secret insight

    def secret_presence(self, keys: Mapping[str, str] | None = None) -> Dict[str, bool]:
        target_keys = keys or {"client_secret": "MSAL client secret"}
        return {
            label: self._secret_store.get_secret(key) is not None
            for key, label in target_keys.items()
        }

    def telemetry_opt_in(self) -> bool:
        path = self._telemetry_pref_path()
        if not path.exists():
            return False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("Telemetry preference file is invalid JSON", path=str(path))
            return False
        return bool(payload.get("telemetry_opt_in", False))

    def set_telemetry_opt_in(self, enabled: bool) -> None:
        path = self._telemetry_pref_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "telemetry_opt_in": bool(enabled),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info("Telemetry preference updated", enabled=enabled)

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

    def _telemetry_pref_path(self) -> Path:
        return config_dir() / "telemetry.json"

    # ----------------------------------------------------------- Bundle helpers

    def _resolve_bundle_path(self, target: Path | None, timestamp: str) -> Path:
        if target is None:
            return log_dir() / f"intune-manager-diagnostics-{timestamp}.tar.xz"
        resolved = target
        if resolved.exists() and resolved.is_dir():
            resolved = resolved / f"intune-manager-diagnostics-{timestamp}.tar.xz"
        if not resolved.suffix:
            resolved = resolved.with_suffix(".tar.xz")
        return resolved

    def _crash_reports(self) -> Iterable[Path]:
        directory = log_dir()
        return sorted(directory.glob("crash-*.log"))

    def _build_metadata(
        self,
        timestamp: str,
        *,
        tenant_id: str | None,
    ) -> Dict[str, Any]:
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "timestamp": timestamp,
            "app_version": self._resolve_version(),
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "tenant_id": tenant_id,
            "config_dir": str(config_dir()),
            "log_dir": str(log_dir()),
        }

    def _cache_summary(self, tenant_id: str | None) -> Dict[str, Any]:
        summary: Dict[str, Any] = {}
        for name, repository in self._repositories.items():
            entry = repository.cache_entry(tenant_id=tenant_id)
            summary[name] = {
                "cached_count": entry.item_count if entry else None,
                "last_refresh": entry.last_refresh.isoformat()
                if entry and entry.last_refresh
                else None,
                "expires_at": entry.expires_at.isoformat()
                if entry and entry.expires_at
                else None,
                "is_stale": repository.is_cache_stale(tenant_id=tenant_id),
            }
            try:
                summary[name]["actual_count"] = repository.count(tenant_id=tenant_id)
            except Exception as exc:  # pragma: no cover - defensive
                summary[name]["actual_count_error"] = str(exc)
        return summary

    def _settings_snapshot(self) -> Dict[str, Any]:
        manager = SettingsManager()
        try:
            settings = manager.load()
        except Exception as exc:  # pragma: no cover - IO errors
            return {"error": str(exc)}
        return {
            "tenant_id": settings.tenant_id,
            "client_id": settings.client_id,
            "authority": settings.authority,
            "redirect_uri": settings.redirect_uri,
            "graph_scopes": list(settings.configured_scopes()),
            "token_cache_path": str(settings.token_cache_path),
        }

    def _serialize_cache_report(self, report: CacheHealthReport) -> Dict[str, Any]:
        return {
            "generated_at": report.generated_at.isoformat(),
            "severity": report.severity.value,
            "entries": [
                {
                    "resource": entry.resource,
                    "scope": entry.scope,
                    "tenant_id": entry.tenant_id,
                    "recorded_count": entry.recorded_count,
                    "actual_count": entry.actual_count,
                    "last_refresh": entry.last_refresh.isoformat()
                    if entry.last_refresh
                    else None,
                    "expires_at": entry.expires_at.isoformat()
                    if entry.expires_at
                    else None,
                    "repaired": entry.repaired,
                    "issues": [
                        {
                            "resource": issue.resource,
                            "scope": issue.scope,
                            "message": issue.message,
                            "severity": issue.severity.value,
                            "detail": issue.detail,
                        }
                        for issue in entry.issues
                    ],
                }
                for entry in report.entries
            ],
            "issues": [
                {
                    "resource": issue.resource,
                    "scope": issue.scope,
                    "message": issue.message,
                    "severity": issue.severity.value,
                    "detail": issue.detail,
                }
                for issue in report.issues
            ],
        }

    def _serialize_attachment_stats(
        self,
        stats: AttachmentStats,
        tenant_id: str | None,
    ) -> Dict[str, Any]:
        return {
            "total_files": stats.total_files,
            "total_bytes": stats.total_bytes,
            "last_modified": stats.last_modified.isoformat()
            if stats.last_modified
            else None,
            "base_dir": str(self._attachments.base_dir(tenant_id=tenant_id)),
        }

    def _add_json(
        self,
        archive: tarfile.TarFile,
        arcname: str,
        payload: Any,
    ) -> None:
        data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        info = tarfile.TarInfo(arcname)
        info.size = len(data)
        info.mtime = time.time()
        archive.addfile(info, io.BytesIO(data))

    @staticmethod
    def _resolve_version() -> str:
        try:
            return version("intune-manager")
        except PackageNotFoundError:  # pragma: no cover - during dev
            return "unknown"


__all__ = ["DiagnosticsService", "AttachmentStats"]
