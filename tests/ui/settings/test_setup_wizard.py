from __future__ import annotations

import pytest
from PySide6.QtCore import QObject, Qt, Signal

from intune_manager.config import Settings
from intune_manager.ui.settings.controller import SettingsSnapshot
from intune_manager.ui.settings.setup_wizard import SetupWizard


class _DummyController(QObject):
    authStatusChanged = Signal(object)
    busyStateChanged = Signal(bool, str)
    infoMessage = Signal(str)
    errorOccurred = Signal(str)
    testConnectionCompleted = Signal(bool, str)

    def __init__(self) -> None:
        super().__init__()
        self._snapshot = SettingsSnapshot(settings=Settings(), has_client_secret=False)

    def load_settings(self) -> SettingsSnapshot:
        return self._snapshot


@pytest.mark.usefixtures("qt_app")
def test_setup_wizard_feedback_uses_plain_text_label() -> None:
    controller = _DummyController()
    wizard = SetupWizard(controller)
    try:
        page = wizard._welcome_page  # type: ignore[attr-defined]
        page.set_feedback("Failure\r\n<script>alert('x')</script>", error=True)
        label = page._feedback_label  # type: ignore[attr-defined]
        assert label.text() == "Failure\n<script>alert('x')</script>"
        assert label.textFormat() == Qt.TextFormat.PlainText
    finally:
        wizard.deleteLater()
