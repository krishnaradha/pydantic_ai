"""Input sanitization and prompt-injection defence for the multi-agent system.

Validation is applied at the system boundary (CLI / API entry point) before any
user-supplied text reaches an agent or is stored in history.

Two threat classes are blocked:

- **Prompt injection** — attempts to override system instructions via user input.
- **Shell injection** — Linux/shell commands embedded in queries that could
  influence code generation in the E2B sandbox.
"""

from __future__ import annotations

import re

from ..config import get_logger
from ..constants import MAX_QUERY_CHARS, MAX_USER_ID_CHARS
from ..exceptions import InputTooLongError, PromptInjectionError

logger = get_logger(__name__)

__all__ = ["validate_query", "validate_user_id", "truncate_tool_output"]

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"you\s+are\s+now\s+(?:a\s+)?(?:an?\s+)?(?:different|new|other)",
        r"disregard\s+(?:all\s+)?(?:prior|previous|above)",
        r"system\s*prompt\s*[:=]",
        r"<\s*/?(?:system|user|assistant)\s*>",
        r"\[\s*(?:system|inst|instruction)\s*\]",
        r"###\s*(?:system|instruction|override)",
    ]
]

_SHELL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\b(rm|rmdir|del|deltree)\s+(-rf?|/s|/q)?\s*[/~\\]",
        r"\b(chmod|chown|chgrp)\s+[0-9]*\s+[/~]",
        r"\b(sudo|su)\s+",
        r"\b(wget|curl)\s+.*\|\s*(sh|bash|zsh|python)",
        r"\b(mkfs|fdisk|dd)\b",
        r">\s*/dev/(sd[a-z]|null|zero|random)",
        r"\b(shutdown|reboot|halt|poweroff)\b",
        r"\beval\s*\(",
        r"\bexec\s*\(",
        r"__import__\s*\(",
        r"\bsubprocess\.(run|call|Popen|check_output)\s*\(",
        r"\bos\.(system|popen|execv|execl|spawnl)\s*\(",
        r":\s*\(\s*\)\s*\{.*\}\s*;",
    ]
]

_USER_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.@]+$")


def validate_query(query: str) -> str:
    """Validate and sanitize a user query before it reaches an agent.

    Checks applied in order: length cap → prompt injection → shell injection.
    Strips leading/trailing whitespace from the returned value.

    Args:
        query: Raw user-supplied query string.

    Returns:
        Stripped, validated query string.

    Raises:
        InputTooLongError: If the query exceeds ``MAX_QUERY_CHARS``.
        PromptInjectionError: If a prompt injection or shell injection pattern is detected.
    """
    stripped = query.strip()

    if len(stripped) > MAX_QUERY_CHARS:
        raise InputTooLongError("query", len(stripped), MAX_QUERY_CHARS)

    for pattern in _INJECTION_PATTERNS:
        if pattern.search(stripped):
            logger.warning("Prompt injection blocked: pattern=%s", pattern.pattern)
            raise PromptInjectionError(pattern.pattern)

    for pattern in _SHELL_PATTERNS:
        if pattern.search(stripped):
            logger.warning("Shell injection blocked: pattern=%s", pattern.pattern)
            raise PromptInjectionError(pattern.pattern)

    return stripped


def validate_user_id(user_id: str) -> str:
    """Validate a user_id to prevent Redis key injection or path traversal.

    Allows alphanumerics and the characters ``_``, ``-``, ``.``, ``@`` only.

    Args:
        user_id: Raw user identifier string.

    Returns:
        The validated user_id unchanged.

    Raises:
        InputTooLongError: If user_id exceeds ``MAX_USER_ID_CHARS``.
        ValueError: If user_id contains disallowed characters.
    """
    if len(user_id) > MAX_USER_ID_CHARS:
        raise InputTooLongError("user_id", len(user_id), MAX_USER_ID_CHARS)

    if not _USER_ID_PATTERN.fullmatch(user_id):
        raise ValueError(
            f"user_id {user_id!r} contains invalid characters. "
            "Allowed: alphanumerics, '_', '-', '.', '@'."
        )

    return user_id


def truncate_tool_output(text: str, max_chars: int) -> str:
    """Truncate tool output before it is fed back to the LLM.

    Prevents a malicious or unexpectedly large retrieval result from exhausting
    the context window.

    Args:
        text: Raw tool output string.
        max_chars: Maximum number of characters to retain.

    Returns:
        Original text if within limit, otherwise truncated with a notice appended.
    """
    if len(text) <= max_chars:
        return text
    logger.warning("Tool output truncated from %d to %d chars", len(text), max_chars)
    return text[:max_chars] + f"\n\n[truncated — {len(text) - max_chars} chars omitted]"
