from __future__ import annotations

import asyncio
import sys

from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from intune_manager.services import ServiceRegistry
from intune_manager.ui import MainWindow
from intune_manager.utils import configure_logging, get_logger


def main() -> None:
    configure_logging()
    logger = get_logger(__name__)
    logger.info("Starting Intune Manager UI shell")

    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    services = ServiceRegistry()
    window = MainWindow(services)
    window.show()

    app.aboutToQuit.connect(loop.stop)

    try:
        with loop:
            loop.run_forever()
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
