from __future__ import annotations

import asyncio
import sys

from intune_manager.utils.crash import CrashReporter


def test_capture_exception_writes_report(tmp_path) -> None:
    reporter = CrashReporter(tmp_path)
    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:  # pragma: no branch - executed by design
        path = reporter.capture_exception(exc)

    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "RuntimeError" in content
    assert "Traceback:" in content


def test_install_and_uninstall_restore_hooks(tmp_path) -> None:
    reporter = CrashReporter(tmp_path)
    original_hook = sys.excepthook
    try:
        reporter.install()
        assert sys.excepthook == reporter._handle_unhandled  # type: ignore[attr-defined]
    finally:
        reporter.uninstall()
    assert sys.excepthook == original_hook


def test_install_sets_asyncio_handler(tmp_path) -> None:
    loop = asyncio.new_event_loop()
    reporter = CrashReporter(tmp_path)
    try:
        reporter.install(loop)
        assert loop.get_exception_handler() == reporter._handle_async_exception  # type: ignore[attr-defined]
    finally:
        reporter.uninstall()
        loop.close()


def test_crash_marker_roundtrip(tmp_path, monkeypatch) -> None:
    logs = tmp_path / "logs"
    runtime = tmp_path / "runtime"
    logs.mkdir(parents=True)
    runtime.mkdir(parents=True)

    monkeypatch.setattr("intune_manager.utils.crash.log_dir", lambda: logs)
    monkeypatch.setattr("intune_manager.utils.crash.runtime_dir", lambda: runtime)

    reporter = CrashReporter()
    try:
        raise RuntimeError("marker")
    except RuntimeError as exc:  # pragma: no branch
        reporter.capture_exception(exc)

    info = reporter.pending_crash()
    assert info is not None
    assert "report_path" in info
    reporter.clear_pending_crash()
    assert reporter.pending_crash() is None
