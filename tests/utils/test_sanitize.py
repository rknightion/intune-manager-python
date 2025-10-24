from __future__ import annotations

from intune_manager.utils.sanitize import sanitize_log_message, sanitize_search_text


def test_sanitize_search_text_removes_sql_control_characters() -> None:
    query = "  Robert'); DROP TABLE devices;--  "
    assert sanitize_search_text(query) == "Robert DROP TABLE devices--"


def test_sanitize_search_text_preserves_safe_symbols() -> None:
    query = "Group admin@example.com /devices"
    assert sanitize_search_text(query) == query.strip()


def test_sanitize_log_message_strips_control_characters() -> None:
    message = "Failure\r\n<script>alert('x')</script>\x08"
    assert sanitize_log_message(message) == "Failure\n<script>alert('x')</script>"
