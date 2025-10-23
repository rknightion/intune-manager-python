from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from intune_manager.config.settings import cache_dir
from intune_manager.utils import get_logger


logger = get_logger(__name__)


@dataclass(slots=True, frozen=True)
class AttachmentMetadata:
    key: str
    path: Path
    size_bytes: int
    last_accessed: datetime
    tenant_id: str | None = None
    category: str | None = None


class AttachmentCache:
    """Disk-backed cache for binary blobs with quota enforcement."""

    def __init__(
        self,
        *,
        base_dir: Path | None = None,
        max_bytes: int = 512 * 1024 * 1024,
        default_ttl: timedelta | None = timedelta(days=7),
    ) -> None:
        self._base_dir = base_dir or (cache_dir() / "attachments")
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._max_bytes = max_bytes
        self._default_ttl = default_ttl

    # ------------------------------------------------------------------ Public

    def store(
        self,
        key: str,
        data: bytes,
        *,
        tenant_id: str | None = None,
        category: str | None = None,
    ) -> AttachmentMetadata:
        path = self._path_for(key, tenant_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_bytes(data)
        tmp_path.replace(path)
        os.utime(path, None)
        self._enforce_quota()
        return AttachmentMetadata(
            key=key,
            path=path,
            size_bytes=path.stat().st_size,
            last_accessed=datetime.utcnow(),
            tenant_id=tenant_id,
            category=category,
        )

    def get(self, key: str, *, tenant_id: str | None = None) -> AttachmentMetadata | None:
        path = self._path_for(key, tenant_id)
        if not path.exists():
            return None
        os.utime(path, None)
        stat = path.stat()
        return AttachmentMetadata(
            key=key,
            path=path,
            size_bytes=stat.st_size,
            last_accessed=datetime.utcfromtimestamp(stat.st_atime),
            tenant_id=tenant_id,
        )

    def delete(self, key: str, *, tenant_id: str | None = None) -> None:
        path = self._path_for(key, tenant_id)
        try:
            path.unlink()
        except FileNotFoundError:  # pragma: no cover - best effort
            return

    def purge(self, *, tenant_id: str | None = None) -> None:
        root = self._tenant_root(tenant_id)
        if root.exists():
            for entry in root.glob("**/*"):
                if entry.is_file():
                    entry.unlink()
        logger.info("Attachment cache purged", tenant_id=tenant_id)

    def base_dir(self, *, tenant_id: str | None = None) -> Path:
        """Return the root directory backing the attachment cache."""

        root = self._tenant_root(tenant_id)
        root.mkdir(parents=True, exist_ok=True)
        return root

    # --------------------------------------------------------------- Helpers

    def _path_for(self, key: str, tenant_id: str | None) -> Path:
        hashed = hashlib.sha256(key.encode("utf-8")).hexdigest()
        subdir = hashed[:2]
        root = self._tenant_root(tenant_id)
        return root / subdir / hashed

    def _tenant_root(self, tenant_id: str | None) -> Path:
        if tenant_id:
            return self._base_dir / tenant_id
        return self._base_dir / "global"

    def _all_files(self) -> Iterable[Path]:
        if not self._base_dir.exists():
            return []
        for path in self._base_dir.rglob("*"):
            if path.is_file():
                yield path

    def _enforce_quota(self) -> None:
        files = list(self._all_files())
        total = sum(path.stat().st_size for path in files)
        if total <= self._max_bytes:
            if self._default_ttl is not None:
                self._purge_expired(files)
            return

        files.sort(key=lambda p: p.stat().st_atime)
        for path in files:
            if total <= self._max_bytes:
                break
            size = path.stat().st_size
            path.unlink(missing_ok=True)
            total -= size
        if self._default_ttl is not None:
            remaining = [p for p in files if p.exists()]
            self._purge_expired(remaining)

    def _purge_expired(self, files: Iterable[Path]) -> None:
        if self._default_ttl is None:
            return
        cutoff = datetime.utcnow() - self._default_ttl
        for path in files:
            try:
                atime = datetime.utcfromtimestamp(path.stat().st_atime)
            except FileNotFoundError:  # pragma: no cover - race
                continue
            if atime < cutoff:
                path.unlink(missing_ok=True)


__all__ = ["AttachmentCache", "AttachmentMetadata"]
