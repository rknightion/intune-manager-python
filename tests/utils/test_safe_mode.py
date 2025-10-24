from __future__ import annotations

from intune_manager.utils.safe_mode import (
    consume_cache_purge_request,
    disable_safe_mode,
    enable_safe_mode,
    request_cache_purge,
    safe_mode_enabled,
    safe_mode_reason,
)


def test_safe_mode_state_transitions() -> None:
    disable_safe_mode()
    assert not safe_mode_enabled()
    assert safe_mode_reason() is None

    enable_safe_mode("Crash detected")
    assert safe_mode_enabled()
    assert safe_mode_reason() == "Crash detected"

    request_cache_purge()
    assert consume_cache_purge_request() is True
    assert consume_cache_purge_request() is False

    disable_safe_mode()
    assert not safe_mode_enabled()
