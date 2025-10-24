from __future__ import annotations

from intune_manager.auth import TokenCacheManager


def test_clear_removes_cache_file(tmp_path) -> None:
    cache_path = tmp_path / "cache.bin"
    cache_path.write_text("{}", encoding="utf-8")

    manager = TokenCacheManager(cache_path)
    assert manager.path == cache_path
    assert cache_path.exists()

    manager.clear()
    assert not cache_path.exists()


def test_clear_handles_missing_file(tmp_path) -> None:
    cache_path = tmp_path / "cache.bin"
    manager = TokenCacheManager(cache_path)

    manager.clear()
    assert not cache_path.exists()
    assert manager.path == cache_path
