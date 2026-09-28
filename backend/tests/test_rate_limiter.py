"""Tests for the rate limiter implementations."""
from __future__ import annotations

import pytest

from app.providers.rate_limiter import InMemoryRateLimiter, NullRateLimiter, RateLimiter


class TestInMemoryRateLimiter:
    def test_satisfies_protocol(self) -> None:
        limiter = InMemoryRateLimiter()
        assert isinstance(limiter, RateLimiter)

    @pytest.mark.asyncio
    async def test_acquire_succeeds_within_capacity(self) -> None:
        limiter = InMemoryRateLimiter(rate=5, period=60.0)
        for _ in range(5):
            assert await limiter.acquire("test") is True

    @pytest.mark.asyncio
    async def test_acquire_fails_when_exhausted(self) -> None:
        limiter = InMemoryRateLimiter(rate=2, period=60.0)
        assert await limiter.acquire("test") is True
        assert await limiter.acquire("test") is True
        assert await limiter.acquire("test") is False

    @pytest.mark.asyncio
    async def test_separate_keys_have_separate_buckets(self) -> None:
        limiter = InMemoryRateLimiter(rate=1, period=60.0)
        assert await limiter.acquire("key_a") is True
        assert await limiter.acquire("key_b") is True
        assert await limiter.acquire("key_a") is False

    @pytest.mark.asyncio
    async def test_wait_and_acquire_timeout(self) -> None:
        limiter = InMemoryRateLimiter(rate=1, period=600.0)
        await limiter.acquire("test")
        with pytest.raises(TimeoutError, match="Rate limit timeout"):
            await limiter.wait_and_acquire("test", timeout=0.2)


class TestNullRateLimiter:
    def test_satisfies_protocol(self) -> None:
        limiter = NullRateLimiter()
        assert isinstance(limiter, RateLimiter)

    @pytest.mark.asyncio
    async def test_always_permits(self) -> None:
        limiter = NullRateLimiter()
        for _ in range(1000):
            assert await limiter.acquire("any_key") is True

    @pytest.mark.asyncio
    async def test_wait_and_acquire_returns_immediately(self) -> None:
        limiter = NullRateLimiter()
        await limiter.wait_and_acquire("any_key")
