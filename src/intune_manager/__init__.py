from __future__ import annotations

import asyncio
import sys

from PySide6.QtWidgets import QApplication, QDialog
from qasync import QEventLoop

from intune_manager.bootstrap import build_services
from intune_manager.ui import MainWindow
from intune_manager.ui.components import CrashRecoveryDialog
from intune_manager.ui.i18n import TranslationManager
from intune_manager.utils import (
    CrashReporter,
    configure_logging,
    consume_cache_purge_request,
    enable_safe_mode,
    get_logger,
    request_cache_purge,
)


def main() -> None:
    configure_logging()
    logger = get_logger(__name__)
    logger.info("Starting Intune Manager UI shell")

    crash_reporter = CrashReporter()
    crash_reporter.install()

    app = QApplication(sys.argv)
    _translations = TranslationManager(app)
    _translations.load()
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    crash_reporter.install(loop)

    if not _handle_crash_recovery(crash_reporter):
        logger.warning("Startup aborted by user during crash recovery prompt")
        crash_reporter.uninstall()
        return

    services = build_services()
    _apply_recovery_actions(services)
    window = MainWindow(services)
    window.show()

    app.aboutToQuit.connect(loop.stop)

    try:
        with loop:
            loop.run_forever()
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    finally:
        crash_reporter.uninstall()


def _handle_crash_recovery(crash_reporter: CrashReporter) -> bool:
    info = crash_reporter.pending_crash()
    if not info:
        return True

    dialog = CrashRecoveryDialog(info)
    result = dialog.exec()
    if result != QDialog.DialogCode.Accepted:
        return False

    decision = dialog.decision()
    reason = info.get("exception_type") or "Previous crash detected"
    if decision.safe_mode:
        enable_safe_mode(reason)
    if decision.purge_cache:
        request_cache_purge()
    crash_reporter.clear_pending_crash()
    return True


def _apply_recovery_actions(services) -> None:
    if not consume_cache_purge_request():
        return
    logger = get_logger(__name__)
    diagnostics = getattr(services, "diagnostics", None)
    if diagnostics is None:
        logger.warning("Cache purge requested but diagnostics service unavailable")
        return
    try:
        diagnostics.clear_all_caches()
        diagnostics.purge_attachments()
        logger.info("Safe mode cache purge completed")
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to purge caches during crash recovery")
