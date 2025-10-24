from __future__ import annotations

import asyncio
import sys

from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from intune_manager.bootstrap import build_services
from intune_manager.ui import MainWindow
from intune_manager.ui.i18n import TranslationManager
from intune_manager.utils import (
    CrashReporter,
    configure_logging,
    consume_cache_purge_request,
    consume_safe_mode_request_marker,
    enable_safe_mode,
    get_logger,
)


def main() -> None:
    configure_logging()
    logger = get_logger(__name__)
    logger.info("Starting Intune Manager UI shell")

    crash_reporter = CrashReporter()
    crash_reporter.install()
    pending_crash = crash_reporter.pending_crash()
    scheduled_safe_mode = consume_safe_mode_request_marker()
    if scheduled_safe_mode:
        reason = scheduled_safe_mode.get("reason") or "Manual request"
        enable_safe_mode(reason)
        logger.warning(
            "Safe mode requested before launch",
            reason=reason,
        )

    app = QApplication(sys.argv)
    _translations = TranslationManager(app)
    _translations.load()
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    crash_reporter.install(loop)
    services = build_services()
    cache_purge_requested = consume_cache_purge_request()
    if cache_purge_requested:
        _apply_cache_purge(services)
    window = MainWindow(services, startup_crash_info=pending_crash)
    window.show()
    if pending_crash:
        crash_reporter.clear_pending_crash()
    app.aboutToQuit.connect(loop.stop)

    try:
        with loop:
            loop.run_forever()
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    finally:
        crash_reporter.uninstall()


def _apply_cache_purge(services) -> None:
    logger = get_logger(__name__)
    diagnostics = getattr(services, "diagnostics", None)
    if diagnostics is None:
        logger.warning(
            "Cache purge was requested but the diagnostics service is unavailable",
        )
        return
    try:
        diagnostics.clear_all_caches()
        diagnostics.purge_attachments()
        logger.info("Startup cache purge completed")
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to purge caches during startup")
