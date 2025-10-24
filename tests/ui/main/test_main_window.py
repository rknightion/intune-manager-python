from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QWidget

from intune_manager.config import FirstRunStatus, Settings
from intune_manager.services import ServiceRegistry
from intune_manager.ui.main.window import MainWindow


class _DummyModule(QWidget):
    """Lightweight widget capturing the UI context provided by MainWindow."""

    def __init__(
        self,
        page_key: str,
        services: ServiceRegistry,
        *,
        context,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.page_key = page_key
        self.services = services
        self.context = context
        self.setObjectName(f"dummy:{page_key}")


class _DummySettingsPage(QWidget):
    """Minimal replacement for the real SettingsPage used in tests."""

    def __init__(
        self,
        *,
        diagnostics,
        services: ServiceRegistry | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.diagnostics = diagnostics
        self.services = services
        self.launch_count = 0

    def launch_setup_wizard(self) -> None:
        self.launch_count += 1


@pytest.fixture
def main_window_builder(monkeypatch: pytest.MonkeyPatch, qtbot):
    """Factory fixture to construct patched MainWindow instances on demand."""

    def _builder(*, crash_info: dict[str, str] | None = None):
        created: dict[str, _DummyModule] = {}

        def _make_stub(page_key: str):
            def _factory(services: ServiceRegistry, *, context, parent=None):
                widget = _DummyModule(page_key, services, context=context, parent=parent)
                created[page_key] = widget
                return widget

            return _factory

        monkeypatch.setattr(
            "intune_manager.ui.main.window.DashboardWidget", _make_stub("dashboard")
        )
        monkeypatch.setattr(
            "intune_manager.ui.main.window.DevicesWidget", _make_stub("devices")
        )
        monkeypatch.setattr(
            "intune_manager.ui.main.window.ApplicationsWidget",
            _make_stub("applications"),
        )
        monkeypatch.setattr(
            "intune_manager.ui.main.window.GroupsWidget", _make_stub("groups")
        )
        monkeypatch.setattr(
            "intune_manager.ui.main.window.AssignmentsWidget",
            _make_stub("assignments"),
        )
        monkeypatch.setattr(
            "intune_manager.ui.main.window.ReportsWidget", _make_stub("reports")
        )
        monkeypatch.setattr(
            "intune_manager.ui.main.window.SettingsPage", _DummySettingsPage
        )

        status = FirstRunStatus(
            is_first_run=False,
            missing_settings=False,
            has_token_cache=True,
            token_cache_path=Path("/tmp/token.cache"),
            settings=Settings(),
        )
        monkeypatch.setattr(
            "intune_manager.ui.main.window.detect_first_run", lambda: status
        )

        window = MainWindow(
            ServiceRegistry(),
            startup_crash_info=crash_info,
        )
        qtbot.addWidget(window)
        window.show()
        qtbot.waitUntil(window.isVisible)

        return window, created

    return _builder


@pytest.fixture
def patched_main_window(main_window_builder):
    return main_window_builder()


def test_main_window_navigation_switches_pages(patched_main_window, qtbot):
    window, created = patched_main_window

    # All navigation pages should have been constructed with a shared UI context.
    assert window.ui_context is not None
    for key in (
        "dashboard",
        "devices",
        "applications",
        "groups",
        "assignments",
        "reports",
    ):
        assert key in created, f"Expected stub page for {key}"
        assert created[key].context is window.ui_context
        assert created[key].services is window._services  # noqa: SLF001 - test access

    for index, item in enumerate(window.NAV_ITEMS):
        window._nav_list.setCurrentRow(index)  # noqa: SLF001 - navigation wiring under test
        qtbot.waitUntil(
            lambda: window._stack.currentWidget() is window._pages[item.key]
        )  # noqa: SLF001
        expected_prefix = "Ready" if index == 0 else item.label
        qtbot.waitUntil(
            lambda: window.statusBar().currentMessage().startswith(expected_prefix)
        )


def test_open_onboarding_uses_settings_page(patched_main_window):
    window, _ = patched_main_window
    settings_page = window._settings_page  # noqa: SLF001 - test verifies wiring
    assert isinstance(settings_page, _DummySettingsPage)
    assert settings_page.launch_count == 0

    window._open_onboarding_setup()  # noqa: SLF001
    assert settings_page.launch_count == 1


def test_previous_crash_surfaces_notification(
    main_window_builder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    messages: list[str] = []

    def _capture(self, message: str, *, level, duration_ms: int = 4500):  # noqa: ANN001
        messages.append(message)

    monkeypatch.setattr(
        MainWindow,
        "show_notification",
        _capture,
        raising=False,
    )

    crash_log = tmp_path / "crash.log"
    crash_log.write_text("boom", encoding="utf-8")
    crash_info = {
        "timestamp": "2025-10-24T18:10:09.051434Z",
        "exception_type": "ValueError",
        "report_path": str(crash_log),
    }

    window, _ = main_window_builder(crash_info=crash_info)
    assert any("ended unexpectedly" in message for message in messages)
    assert window._crash_report_path == crash_log  # noqa: SLF001 - verifies wiring
