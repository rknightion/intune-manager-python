from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from typing import Generator

import pytest
from PySide6.QtWidgets import QApplication

from intune_manager.data import DatabaseConfig, DatabaseManager


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Provide a dedicated event loop for pytest-asyncio."""

    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


@pytest.fixture(scope="session")
def qt_app() -> Iterator[QApplication]:
    """Ensure a QApplication instance exists for UI tests."""

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def database(tmp_path) -> Iterator[DatabaseManager]:
    """Create an isolated SQLite database for repository tests."""

    db_path = tmp_path / "cache.db"
    config = DatabaseConfig(path=db_path)
    manager = DatabaseManager(config)
    manager.ensure_schema()
    yield manager
