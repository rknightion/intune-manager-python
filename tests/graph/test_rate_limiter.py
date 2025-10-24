from __future__ import annotations

import asyncio

import pytest

import intune_manager.graph.rate_limiter as rate_limiter_module
from intune_manager.graph.errors import GraphAPIError, GraphErrorCategory
from intune_manager.graph.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_can_make_request_respects_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = RateLimiter()
    limiter.max_total_requests_per_window = 2
    limiter.max_write_requests_per_window = 1
    base_time = 1.0
    monkeypatch.setattr(limiter, "_now", lambda: base_time)

    await limiter.record_request(is_write=False)
    await limiter.record_request(is_write=True)

    allowed_total = await limiter.can_make_request(is_write=False)
    allowed_write = await limiter.can_make_request(is_write=True)
    assert not allowed_total
    assert not allowed_write

    # Advance time beyond rolling window to trigger cleanup and allow requests again.
    monkeypatch.setattr(
        limiter,
        "_now",
        lambda: base_time + limiter.window_seconds + 1,
    )
    assert await limiter.can_make_request(is_write=True)


@pytest.mark.asyncio
async def test_calculate_delay_and_rate_limit_tracking(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = RateLimiter()
    limiter.max_total_requests_per_window = 10
    base_time = 100.0
    monkeypatch.setattr(limiter, "_now", lambda: base_time)

    for _ in range(9):
        await limiter.record_request(is_write=False)

    delay = await limiter.calculate_delay(is_write=False)
    assert delay > 0.0

    await limiter.record_rate_limit()
    extra_delay = await limiter.calculate_delay(is_write=False)
    # Rate limit bump adds at least 2 seconds.
    assert extra_delay >= 2.0

    await limiter.reset_rate_limit_tracking()
    monkeypatch.setattr(
        limiter,
        "_now",
        lambda: base_time + limiter.window_seconds + 1,
    )
    assert await limiter.calculate_delay(is_write=False) == 0.0


@pytest.mark.asyncio
async def test_calculate_retry_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = RateLimiter()

    delay = await limiter.calculate_retry_delay(attempt=1, retry_after_header="7")
    assert delay == 7.0

    monkeypatch.setattr("random.uniform", lambda _a, _b: 1.0)
    delay_no_header = await limiter.calculate_retry_delay(attempt=3)
    expected = min(
        limiter.base_retry_delay * (2 ** (3 - 1)) * 1.0,
        limiter.max_retry_delay,
    )
    assert delay_no_header == expected


@pytest.mark.asyncio
async def test_should_retry_conditions() -> None:
    limiter = RateLimiter()

    assert await limiter.should_retry(
        attempt=1,
        error=asyncio.TimeoutError(),
    )

    rate_limit_error = GraphAPIError(
        message="429",
        category=GraphErrorCategory.RATE_LIMIT,
    )
    assert await limiter.should_retry(attempt=1, error=rate_limit_error)
    assert not await limiter.should_retry(
        attempt=limiter.max_retries + 1,
        error=rate_limit_error,
    )

    unknown_error = GraphAPIError(
        message="Validation failed",
        category=GraphErrorCategory.VALIDATION,
    )
    assert not await limiter.should_retry(attempt=1, error=unknown_error)


@pytest.mark.asyncio
async def test_split_into_batches_respects_capacity(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = RateLimiter()
    limiter.max_total_requests_per_window = 5
    limiter.max_write_requests_per_window = 4
    base_time = 500.0
    monkeypatch.setattr(limiter, "_now", lambda: base_time)

    await limiter.record_request(is_write=True)
    await limiter.record_request(is_write=False)

    batch_size = await limiter.calculate_optimal_batch_size()
    assert batch_size == 2

    items = list(range(5))
    batches = await limiter.split_into_batches(items, is_write=True)
    assert len(batches) == 3
    assert [len(batch) for batch in batches] == [2, 2, 1]
