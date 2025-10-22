from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable, Protocol

from intune_manager.data import (
    AuditEventRepository,
    DeviceRepository,
    MobileAppRepository,
)
from intune_manager.services.base import EventHook
from intune_manager.utils import get_logger


logger = get_logger(__name__)


class GraphSerializable(Protocol):
    def to_graph(self) -> dict: ...


class ExportService:
    """Generate CSV/JSON exports from cached repositories."""

    def __init__(
        self,
        *,
        devices: DeviceRepository,
        apps: MobileAppRepository,
        audits: AuditEventRepository,
    ) -> None:
        self._devices = devices
        self._apps = apps
        self._audits = audits

        self.completed: EventHook[Path] = EventHook()

    def export_devices_csv(self, path: Path, *, tenant_id: str | None = None) -> Path:
        devices = self._devices.list_all(tenant_id=tenant_id)
        self._write_csv(path, devices)
        logger.debug("Exported devices CSV", path=str(path), count=len(devices))
        self.completed.emit(path)
        return path

    def export_apps_csv(self, path: Path, *, tenant_id: str | None = None) -> Path:
        apps = self._apps.list_all(tenant_id=tenant_id)
        self._write_csv(path, apps)
        logger.debug("Exported apps CSV", path=str(path), count=len(apps))
        self.completed.emit(path)
        return path

    def export_audit_events_json(self, path: Path, *, tenant_id: str | None = None) -> Path:
        events = self._audits.list_all(tenant_id=tenant_id)
        payload = [event.to_graph() for event in events]
        path.write_text(json.dumps(payload, indent=2))
        logger.debug("Exported audit events JSON", path=str(path), count=len(events))
        self.completed.emit(path)
        return path

    def _write_csv(self, path: Path, items: Iterable[GraphSerializable]) -> None:
        rows = [item.to_graph() for item in items]
        if not rows:
            path.write_text("")
            return
        header = sorted({key for row in rows for key in row.keys()})
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=header)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)


__all__ = ["ExportService"]
