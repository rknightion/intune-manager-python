from __future__ import annotations

import pytest

from intune_manager.utils.safe_mode import (
    cancel_cache_purge_request,
    cancel_safe_mode_request,
    consume_cache_purge_request,
    consume_safe_mode_request_marker,
    disable_safe_mode,
    enable_safe_mode,
    pending_cache_purge_request,
    pending_safe_mode_request,
    request_cache_purge,
    safe_mode_enabled,
    safe_mode_reason,
    schedule_cache_purge_request,
    schedule_safe_mode_request,
)


@pytest.fixture
def runtime_tmp(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(
        "intune_manager.utils.safe_mode.runtime_dir",
        lambda: tmp_path,
    )
    yield tmp_path


def test_safe_mode_state_transitions(runtime_tmp) -> None:
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


def test_schedule_safe_mode_request(runtime_tmp) -> None:
    schedule_safe_mode_request("Diagnostics tab")
    info = pending_safe_mode_request()
    assert info is not None
    assert info["reason"] == "Diagnostics tab"
    consumed = consume_safe_mode_request_marker()
    assert consumed is not None
    assert consumed["reason"] == "Diagnostics tab"
    assert pending_safe_mode_request() is None


def test_cancel_safe_mode_request(runtime_tmp) -> None:
    schedule_safe_mode_request("Manual")
    cancel_safe_mode_request()
    assert pending_safe_mode_request() is None


def test_schedule_cache_purge_request(runtime_tmp) -> None:
    schedule_cache_purge_request("Diagnostics")
    info = pending_cache_purge_request()
    assert info is not None
    assert info["reason"] == "Diagnostics"
    assert consume_cache_purge_request() is True
    assert pending_cache_purge_request() is None


def test_cancel_cache_purge_request(runtime_tmp) -> None:
    schedule_cache_purge_request("Manual purge")
    cancel_cache_purge_request()
    assert pending_cache_purge_request() is None
