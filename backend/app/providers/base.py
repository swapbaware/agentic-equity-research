"""Provider base class with retry, timeout, tracing, and health checks.

Concrete providers inherit from ProviderBase to get cross-cutting concerns
for free. Protocol interfaces remain the structural contract — ProviderBase
is an implementation convenience, not a requirement.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TypeVar

from app.providers.errors import (
    ProviderAuthError,
    ProviderDataError,
    ProviderError,
    ProviderNotFoundError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.providers.rate_limiter import RateLimiter
from app.providers.types import ProviderHealth

_T = TypeVar("_T")


@dataclass(frozen=True)
class ProviderConfig:
    """Configuration for a single provider instance."""

    provider_name: str
    default_timeout: float = 30.0
    max_retries: int = 3
    base_retry_delay: float = 1.0
    max_retry_delay: float = 60.0
    rate_limit_requests: float = 100.0
    rate_limit_period: float = 60.0
    extra: dict[str, str] = field(default_factory=dict)


class ProviderBase:
    """Shared infrastructure for provider implementations."""

    def __init__(
        self,
        config: ProviderConfig,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self._config = config
        self._rate_limiter = rate_limiter
        self._logger = logging.getLogger(f"provider.{config.provider_name}")

    @property
    def provider_name(self) -> str:
        return self._config.provider_name

    async def _execute(
        self,
        operation: str,
        fn: Callable[[], Awaitable[_T]],
        *,
        timeout: float | None = None,
    ) -> _T:
        """Execute a provider call with retry, rate limiting, timeout, and tracing."""
        effective_timeout = timeout or self._config.default_timeout
        last_error: ProviderError | None = None

        for attempt in range(1, self._config.max_retries + 1):
            if self._rate_limiter is not None:
                await self._rate_limiter.acquire(self._config.provider_name)

            start = time.monotonic()
            try:
                result = await asyncio.wait_for(fn(), timeout=effective_timeout)
                elapsed_ms = (time.monotonic() - start) * 1000
                self._logger.info(
                    "%s.%s succeeded attempt=%d latency=%.1fms",
                    self._config.provider_name,
                    operation,
                    attempt,
                    elapsed_ms,
                )
                return result

            except TimeoutError:
                elapsed_ms = (time.monotonic() - start) * 1000
                last_error = ProviderTimeoutError(
                    provider=self._config.provider_name,
                    operation=operation,
                    timeout=effective_timeout,
                )
                self._logger.warning(
                    "%s.%s timed out attempt=%d latency=%.1fms timeout=%.1fs",
                    self._config.provider_name,
                    operation,
                    attempt,
                    elapsed_ms,
                    effective_timeout,
                )

            except ProviderRateLimitError as e:
                last_error = e
                delay = e.retry_after if e.retry_after else self._backoff_delay(attempt)
                self._logger.warning(
                    "%s.%s rate limited attempt=%d retry_after=%.1fs",
                    self._config.provider_name,
                    operation,
                    attempt,
                    delay,
                )
                if attempt < self._config.max_retries:
                    await asyncio.sleep(delay)
                    continue
                raise

            except ProviderUnavailableError as e:
                elapsed_ms = (time.monotonic() - start) * 1000
                last_error = e
                self._logger.warning(
                    "%s.%s unavailable attempt=%d latency=%.1fms",
                    self._config.provider_name,
                    operation,
                    attempt,
                    elapsed_ms,
                )

            except (ProviderAuthError, ProviderNotFoundError, ProviderDataError):
                raise

            except ProviderError:
                raise

            except Exception as exc:
                raise ProviderError(
                    provider=self._config.provider_name,
                    message=f"Unexpected error in {operation}: {exc}",
                    operation=operation,
                ) from exc

            if attempt < self._config.max_retries:
                delay = self._backoff_delay(attempt)
                await asyncio.sleep(delay)

        assert last_error is not None  # noqa: S101
        raise last_error

    def _backoff_delay(self, attempt: int) -> float:
        delay = self._config.base_retry_delay * (2 ** (attempt - 1))
        return min(delay, self._config.max_retry_delay)

    async def check_health(self) -> ProviderHealth:
        """Default health check — subclasses should override with a real probe."""
        return ProviderHealth(
            provider_name=self._config.provider_name,
            is_healthy=True,
            message="default health check (no probe)",
            checked_at=datetime.now(UTC),
        )
