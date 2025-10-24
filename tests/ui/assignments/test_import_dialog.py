from __future__ import annotations

import pytest

from intune_manager.services.assignment_import import AssignmentImportResult
from intune_manager.ui.assignments.import_dialog import AssignmentImportDialog


@pytest.mark.usefixtures("qt_app")
def test_import_dialog_log_text_sanitises_entries(tmp_path) -> None:
    result = AssignmentImportResult(
        rows=[],
        assignments_by_app={},
        warnings=["Warn\r\n<script>alert(1)</script>"],
        errors=["Failure\x00 occurred"],
    )

    dialog = AssignmentImportDialog(
        result,
        expected_app_name=None,
        expected_app_id=None,
        source_path=None,
    )
    try:
        text = dialog._build_log_text()
    finally:
        dialog.deleteLater()

    assert "\r" not in text
    assert "\x00" not in text
    assert "<script>alert(1)</script>" in text
