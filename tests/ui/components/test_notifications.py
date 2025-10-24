from __future__ import annotations

import pytest
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from intune_manager.ui.components.notifications import ToastLevel, ToastManager
from intune_manager.ui.components.overlays import BusyOverlay


@pytest.mark.usefixtures("qt_app")
def test_toast_manager_auto_dismisses_toast(qtbot):
    parent = QWidget()
    layout = QVBoxLayout(parent)
    layout.addStretch()
    manager = ToastManager(parent, margin=0)

    qtbot.addWidget(parent)
    parent.show()

    manager.show_toast("Operation complete", level=ToastLevel.SUCCESS, duration_ms=50)
    container = manager._container  # noqa: SLF001 - verifying internal container state
    qtbot.waitUntil(lambda: container.isVisible())
    assert container.layout().count() == 1  # noqa: SLF001

    qtbot.wait(400)  # allow fade-out animation + timer to complete
    assert container.layout().count() == 0  # noqa: SLF001
    assert container.isHidden()


@pytest.mark.usefixtures("qt_app")
def test_busy_overlay_blocks_interactions(qtbot):
    parent = QWidget()
    layout = QVBoxLayout(parent)
    button = QPushButton("Click me")
    layout.addWidget(button)
    parent.resize(200, 100)
    qtbot.addWidget(parent)
    parent.show()

    center = button.rect().center()
    pos = button.mapTo(parent, center)
    assert parent.childAt(pos) is button

    overlay = BusyOverlay(parent, default_message="Processing…")
    overlay.show_overlay("Working…")
    qtbot.waitUntil(overlay.isVisible)
    child = parent.childAt(pos)
    probe = child
    while probe is not None and probe is not overlay:
        probe = probe.parent()
    assert probe is overlay

    overlay.hide_overlay()
    qtbot.waitUntil(lambda: not overlay.isVisible())
    assert parent.childAt(pos) is button
