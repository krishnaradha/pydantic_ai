"""Retry decorators with exponential backoff for external service calls.

Uses ``tenacity`` under the hood. Import the pre-configured decorators rather
than constructing ``tenacity.retry`` instances inline — keeps retry policy in
one place and keeps call sites clean.

Example:
    ::

        @retry_transient
        async def call_external() -> str:
            ...
"""

from __future__ import annotations

from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from ..config import get_logger
from ..constants import MAX_TOOL_RETRIES

logger = get_logger(__name__)

__all__ = ["retry_transient", "retry_llm"]

_TRANSIENT_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OSError,
)


def _log_retry(retry_state: RetryCallState) -> None:
    fn_name = getattr(retry_state.fn, "__name__", "unknown")
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    logger.warning(
        "Retrying %s (attempt %d): %s",
        fn_name,
        retry_state.attempt_number,
        exc,
    )


retry_transient = retry(
    reraise=True,
    stop=stop_after_attempt(MAX_TOOL_RETRIES),
    wait=wait_exponential_jitter(initial=0.5, max=30, jitter=1),
    retry=retry_if_exception_type(_TRANSIENT_EXCEPTIONS),
    before_sleep=_log_retry,
)
"""Retry up to MAX_TOOL_RETRIES attempts on transient network/OS errors with exponential backoff."""

retry_llm = retry(
    reraise=True,
    stop=stop_after_attempt(MAX_TOOL_RETRIES),
    wait=wait_exponential_jitter(initial=2, max=60, jitter=2),
    retry=retry_if_exception_type(_TRANSIENT_EXCEPTIONS),
    before_sleep=_log_retry,
)
"""Retry up to MAX_TOOL_RETRIES attempts for LLM/embedding API calls with longer backoff."""
