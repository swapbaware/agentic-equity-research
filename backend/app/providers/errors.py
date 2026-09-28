"""Provider error hierarchy.

All provider implementations raise errors from this hierarchy.
Business logic catches ProviderError, never vendor-specific exceptions.
"""
from __future__ import annotations


class ProviderError(Exception):
    """Base error for all provider failures."""

    def __init__(
        self,
        *,
        provider: str,
        message: str,
        operation: str | None = None,
        request_id: str | None = None,
    ) -> None:
        self.provider = provider
        self.operation = operation
        self.request_id = request_id
        super().__init__(message)


class ProviderAuthError(ProviderError):
    """401/403 — invalid or expired credentials."""


class ProviderRateLimitError(ProviderError):
    """429 — rate limit exceeded."""

    def __init__(
        self,
        *,
        provider: str,
        message: str = "Rate limit exceeded",
        retry_after: float | None = None,
        operation: str | None = None,
        request_id: str | None = None,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(
            provider=provider,
            message=message,
            operation=operation,
            request_id=request_id,
        )


class ProviderNotFoundError(ProviderError):
    """404 — requested resource does not exist (company, filing, etc.)."""


class ProviderTimeoutError(ProviderError):
    """Request timed out."""

    def __init__(
        self,
        *,
        provider: str,
        operation: str | None = None,
        timeout: float,
        request_id: str | None = None,
    ) -> None:
        self.timeout = timeout
        super().__init__(
            provider=provider,
            message=f"Request timed out after {timeout:.1f}s",
            operation=operation,
            request_id=request_id,
        )


class ProviderUnavailableError(ProviderError):
    """5xx — provider service is down or degraded."""


class ProviderDataError(ProviderError):
    """Response does not match expected schema or contains invalid data."""
