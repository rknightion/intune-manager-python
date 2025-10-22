from __future__ import annotations

import asyncio
import random
import time
from collections import deque
from typing import Deque, List, Sequence, TypeVar

from intune_manager.graph.errors import GraphAPIError, GraphErrorCategory
from intune_manager.utils import get_logger


_logger = get_logger(__name__)

T = TypeVar("T")


class RateLimiter:
    """Asynchronous rate limiter mirroring Intune Graph constraints."""

    max_write_requests_per_window: int = 100
    max_total_requests_per_window: int = 1000
    window_seconds: float = 20.0

    max_retries: int = 3
    base_retry_delay: float = 1.0
    max_retry_delay: float = 32.0

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._request_times: Deque[float] = deque()
        self._write_request_times: Deque[float] = deque()
        self._last_rate_limit_time: float | None = None
        self._consecutive_rate_limits = 0

    @staticmethod
    def _now() -> float:
        return time.monotonic()

    async def can_make_request(self, *, is_write: bool) -> bool:
        async with self._lock:
            self._cleanup_locked()
            total = len(self._request_times)
            write_count = len(self._write_request_times)

            if total >= self.max_total_requests_per_window:
                _logger.debug(
                    "Approaching total rate limit",
                    total=total,
                    limit=self.max_total_requests_per_window,
                )
                return False

            if is_write and write_count >= self.max_write_requests_per_window:
                _logger.debug(
                    "Approaching write rate limit",
                    write=write_count,
                    limit=self.max_write_requests_per_window,
                )
                return False
            return True

    async def record_request(self, *, is_write: bool) -> None:
        async with self._lock:
            now = self._now()
            self._request_times.append(now)
            if is_write:
                self._write_request_times.append(now)

            if len(self._request_times) > self.max_total_requests_per_window * 2:
                self._cleanup_locked()

    async def record_rate_limit(self) -> None:
        async with self._lock:
            self._last_rate_limit_time = self._now()
            self._consecutive_rate_limits += 1
            _logger.warning(
                "Rate limit encountered",
                consecutive=self._consecutive_rate_limits,
            )

    async def reset_rate_limit_tracking(self) -> None:
        async with self._lock:
            if self._consecutive_rate_limits:
                _logger.info("Resetting rate limit tracking")
            self._consecutive_rate_limits = 0

    async def calculate_delay(self, *, is_write: bool) -> float:
        async with self._lock:
            self._cleanup_locked()

            if (
                self._last_rate_limit_time is not None
                and self._now() - self._last_rate_limit_time < 60
            ):
                extra = min(self._consecutive_rate_limits * 2.0, 10.0)
                return extra

            total = len(self._request_times)
            write_count = len(self._write_request_times)

            if is_write:
                utilization = write_count / self.max_write_requests_per_window
                if utilization > 0.8:
                    return 0.5 * (utilization - 0.8) * 10

            utilization_total = total / self.max_total_requests_per_window
            if utilization_total > 0.8:
                return 0.5 * (utilization_total - 0.8) * 10

            return 0.0

    async def calculate_retry_delay(
        self,
        *,
        attempt: int,
        retry_after_header: str | None = None,
    ) -> float:
        if retry_after_header:
            try:
                header_delay = float(retry_after_header)
                _logger.info("Using Retry-After header", delay=header_delay)
                return header_delay
            except ValueError:
                _logger.debug("Invalid Retry-After header", header=retry_after_header)

        exponential = self.base_retry_delay * (2 ** max(0, attempt - 1))
        jitter = exponential * random.uniform(0.8, 1.2)
        delay: float = min(jitter, self.max_retry_delay)
        _logger.info("Calculated retry delay", delay=delay, attempt=attempt)
        return delay

    async def should_retry(self, *, attempt: int, error: Exception) -> bool:
        if attempt > self.max_retries:
            _logger.warning("Maximum retries exceeded", attempt=attempt)
            return False

        if isinstance(error, asyncio.TimeoutError):
            return True

        if isinstance(error, GraphAPIError):
            if error.category in {
                GraphErrorCategory.RATE_LIMIT,
                GraphErrorCategory.NETWORK,
            }:
                return True
            if error.is_retriable:
                return True
            return False

        message = str(error).lower()
        if any(code in message for code in ("429", "rate", "timeout")):
            return True
        if any(code in message for code in ("500", "502", "503", "504")):
            return True
        return False

    async def calculate_optimal_batch_size(self) -> int:
        async with self._lock:
            self._cleanup_locked()
            remaining_total = self.max_total_requests_per_window - len(
                self._request_times
            )
            remaining_write = self.max_write_requests_per_window - len(
                self._write_request_times
            )
            capacity = max(1, min(remaining_total, remaining_write))
            safe_capacity = int(capacity * 0.8)
            return max(1, min(safe_capacity, 20))

    async def split_into_batches(
        self, items: Sequence[T], *, is_write: bool
    ) -> List[List[T]]:
        batch_size = await self.calculate_optimal_batch_size()
        batches = [
            list(items[i : i + batch_size]) for i in range(0, len(items), batch_size)
        ]
        _logger.info(
            "Split items into batches",
            total=len(items),
            batches=len(batches),
            batch_size=batch_size,
            write=is_write,
        )
        return batches

    def _cleanup_locked(self) -> None:
        cutoff = self._now() - self.window_seconds
        while self._request_times and self._request_times[0] < cutoff:
            self._request_times.popleft()
        while self._write_request_times and self._write_request_times[0] < cutoff:
            self._write_request_times.popleft()


rate_limiter = RateLimiter()

__all__ = ["RateLimiter", "rate_limiter"]
