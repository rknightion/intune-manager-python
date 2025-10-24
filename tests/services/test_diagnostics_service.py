from __future__ import annotations

import json
import tarfile
from pathlib import Path

from intune_manager.config.settings import Settings
from intune_manager.data.storage.attachments import AttachmentCache
from intune_manager.services.diagnostics import DiagnosticsService


class _DummySettingsManager:
    def load(self) -> Settings:
        return Settings(
            tenant_id="contoso.onmicrosoft.com",
            client_id="01234567-89ab-cdef-0123-456789abcdef",
            redirect_uri="http://localhost:8400",
        )


def test_create_diagnostic_bundle_generates_tarball(
    tmp_path,
    database,
    monkeypatch,
) -> None:
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True)
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)

    (logs_dir / "app.log").write_text("Example log entry\n", encoding="utf-8")
    (logs_dir / "crash-20240101.log").write_text("Crash details\n", encoding="utf-8")

    monkeypatch.setattr(
        "intune_manager.services.diagnostics.log_dir", lambda: logs_dir
    )
    monkeypatch.setattr(
        "intune_manager.services.diagnostics.config_dir", lambda: config_dir
    )
    monkeypatch.setattr(
        "intune_manager.services.diagnostics.SettingsManager",
        lambda: _DummySettingsManager(),
    )

    attachments = AttachmentCache(base_dir=tmp_path / "attachments")
    service = DiagnosticsService(database, attachments)

    bundle_path = service.create_diagnostic_bundle(tmp_path)
    assert bundle_path.exists()
    assert bundle_path.suffix == ".xz"

    with tarfile.open(bundle_path, "r:xz") as archive:
        members = {member.name for member in archive.getmembers()}
        assert "metadata.json" in members
        assert "cache/health.json" in members
        assert "attachments/stats.json" in members
        assert "config/settings.json" in members
        assert any(name.startswith("logs/") for name in members)

        metadata_file = archive.extractfile("metadata.json")
        assert metadata_file is not None
        metadata = json.loads(metadata_file.read().decode("utf-8"))
        assert metadata["app_version"]
        assert metadata["log_dir"] == str(logs_dir)

        settings_file = archive.extractfile("config/settings.json")
        assert settings_file is not None
        settings_payload = json.loads(settings_file.read().decode("utf-8"))
        assert settings_payload["tenant_id"] == "contoso.onmicrosoft.com"
