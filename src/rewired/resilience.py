"""Retry and resilience utilities for external API calls.

Provides a ``@retry_on_transient`` decorator for data fetchers that
retries on network-level errors (timeouts, connection resets, 5xx)
without retrying on business logic errors (invalid tickers, auth).
"""

from __future__ import annotations

import logging

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

logger = logging.getLogger(__name__)

# Exception types that indicate transient network/server issues.
# We intentionally exclude OSError (too broad — includes HTTPError)
# and use only network-level exception types.
_TRANSIENT_EXCEPTIONS: tuple[type[Exception], ...] = (
    ConnectionError,
    TimeoutError,
)

# Try to include requests-specific exceptions if available
try:
    import requests.exceptions

    _TRANSIENT_EXCEPTIONS = (
        *_TRANSIENT_EXCEPTIONS,
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.ChunkedEncodingError,
    )
except ImportError:
    pass


def retry_on_transient(fn=None, *, max_attempts: int = 3):
    """Decorator: retry on transient network errors with exponential backoff.

    - 3 attempts by default (1 original + 2 retries)
    - Exponential backoff: 1s, 2s, 4s (capped at 10s)
    - Only retries on network-level errors, not business logic errors
    - Logs a WARNING before each retry
    """
    decorator = retry(
        retry=retry_if_exception_type(_TRANSIENT_EXCEPTIONS),
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    if fn is not None:
        return decorator(fn)
    return decorator
