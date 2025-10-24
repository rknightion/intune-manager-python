from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from typing import Callable, Generator

import pytest
from PySide6.QtWidgets import QApplication
from pytest import FixtureRequest

from intune_manager.data import DatabaseConfig, DatabaseManager
from tests.graph.mocks import GraphMockRepository, register_graph_mocks
from tests.graph.mocks.repository import load_default_repository


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


@pytest.fixture(scope="session")
def graph_mock_repository() -> GraphMockRepository:
    """Load the canonical Graph mock dataset for reuse across tests."""

    return load_default_repository()


@pytest.fixture
def graph_mock_respx(graph_mock_repository: GraphMockRepository, respx_mock):
    """Catch-all mock for Graph requests backed by the shared dataset."""

    responder = register_graph_mocks(respx_mock, graph_mock_repository)
    yield responder
    responder.assert_all_matched()


@pytest.fixture
def ensure_graph_mock(
    request: FixtureRequest,
    graph_mock_repository: GraphMockRepository,
) -> Callable[[str, str], None]:
    """Activate official Graph mock responder or skip if endpoint missing."""

    def _ensure(method: str, url: str) -> None:
        match = graph_mock_repository.match(method.upper(), url)
        if match is None:
            pytest.skip(
                f"No official Graph mock for {method.upper()} {url}; "
                "refresh upstream datasets or add bespoke coverage.",
            )
        request.getfixturevalue("graph_mock_respx")

    return _ensure
