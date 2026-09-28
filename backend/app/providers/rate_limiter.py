"""Token-bucket rate limiter.

InMemoryRateLimiter is used for testing and local development.
A Redis-backed implementation can be added when real providers are integrated.
"""
from __future__ import annotations

import asyncio
import time
from typing import Protocol, runtime_checkable


@runtime_checkable
class RateLimiter(Protocol):
    """Rate limiter interface — any backend must satisfy this."""

    async def acquire(self, key: str, tokens: int = 1) -> bool:
        """Try to acquire tokens. Returns True if allowed, False if exhausted."""
        ...

    async def wait_and_acquire(self, key: str, tokens: int = 1, *, timeout: float = 30.0) -> None:
        """Block until tokens are available or timeout is reached."""
        ...


class InMemoryRateLimiter:
    """In-memory token bucket rate limiter for testing and single-process use."""

    def __init__(self, rate: float = 100.0, period: float = 60.0) -> None:
        self._rate = rate
        self._period = period
        self._buckets: dict[str, _Bucket] = {}

    def _get_bucket(self, key: str) -> _Bucket:
        if key not in self._buckets:
            self._buckets[key] = _Bucket(capacity=self._rate, refill_period=self._period)
        return self._buckets[key]

    async def acquire(self, key: str, tokens: int = 1) -> bool:
        bucket = self._get_bucket(key)
        return bucket.try_consume(tokens)

    async def wait_and_acquire(self, key: str, tokens: int = 1, *, timeout: float = 30.0) -> None:
        deadline = time.monotonic() + timeout
        while True:
            if await self.acquire(key, tokens):
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                msg = f"Rate limit timeout after {timeout:.1f}s for {key}"
                raise TimeoutError(msg)
            await asyncio.sleep(min(0.1, remaining))


class NullRateLimiter:
    """No-op rate limiter — always permits. Used in tests that don't need limiting."""

    async def acquire(self, key: str, tokens: int = 1) -> bool:
        return True

    async def wait_and_acquire(self, key: str, tokens: int = 1, *, timeout: float = 30.0) -> None:
        return


class _Bucket:
    """Single token bucket with gradual refill."""

    def __init__(self, capacity: float, refill_period: float) -> None:
        self._capacity = capacity
        self._refill_rate = capacity / refill_period
        self._tokens = capacity
        self._last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_rate)
        self._last_refill = now

    def try_consume(self, tokens: int) -> bool:
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False
