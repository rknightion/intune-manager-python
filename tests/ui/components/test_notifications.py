from __future__ import annotations

import pytest

from PySide6.QtCore import Qt

from intune_manager.ui.components.notifications import ToastMessage, ToastWidget


@pytest.mark.usefixtures("qtbot")
def test_toast_dismiss_button_closes(qtbot):
    toast = ToastWidget(ToastMessage(text="Error"))
    qtbot.addWidget(toast)
    toast.show()

    qtbot.mouseClick(toast.dismiss_button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: not toast.isVisible())
