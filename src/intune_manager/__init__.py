from __future__ import annotations

import asyncio
import sys

from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from intune_manager.bootstrap import build_services
from intune_manager.ui import MainWindow
from intune_manager.ui.i18n import TranslationManager
from intune_manager.utils import CrashReporter, configure_logging, get_logger


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

    services = build_services()
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
