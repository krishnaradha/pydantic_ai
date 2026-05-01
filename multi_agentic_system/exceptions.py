"""Typed exceptions for the multi-agent system.

All public exceptions inherit from :class:`AgentSystemError` so callers can
catch the entire family with a single ``except AgentSystemError`` clause while
still being able to narrow by subtype when needed.
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "AgentSystemError",
    "DocumentNotFoundError",
    "UnsupportedFileTypeError",
    "VectorStoreError",
    "AgentRunError",
    "InputTooLongError",
    "PromptInjectionError",
]


class AgentSystemError(Exception):
    """Base class for all multi-agent system errors."""


class DocumentNotFoundError(AgentSystemError):
    """Raised when no supported documents are found under the given path.

    Attributes:
        path: The directory that was scanned.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"No .txt or .pdf files found under {path}")


class UnsupportedFileTypeError(AgentSystemError):
    """Raised when a document has an extension the pipeline cannot handle.

    Attributes:
        suffix: The unsupported file extension (e.g. ``'.docx'``).
    """

    def __init__(self, suffix: str) -> None:
        self.suffix = suffix
        super().__init__(
            f"Unsupported file type {suffix!r} — supported types: .txt, .pdf"
        )


class VectorStoreError(AgentSystemError):
    """Raised for unrecoverable ChromaDB operations."""


class AgentRunError(AgentSystemError):
    """Raised when an agent run fails after exhausting retries.

    Attributes:
        agent_name: Name of the agent that failed.
    """

    def __init__(self, agent_name: str, cause: BaseException) -> None:
        self.agent_name = agent_name
        super().__init__(f"Agent '{agent_name}' run failed: {cause}")


class InputTooLongError(AgentSystemError):
    """Raised when a user-supplied input exceeds the allowed character limit.

    Attributes:
        field: Name of the field that was too long.
        actual: Actual character count.
        limit: Maximum allowed character count.
    """

    def __init__(self, field: str, actual: int, limit: int) -> None:
        self.field = field
        self.actual = actual
        self.limit = limit
        super().__init__(
            f"{field} is too long ({actual} chars); maximum allowed is {limit} chars"
        )


class PromptInjectionError(AgentSystemError):
    """Raised when a prompt injection pattern is detected in user input.

    Attributes:
        pattern: The regex pattern that triggered the detection.
    """

    def __init__(self, pattern: str) -> None:
        self.pattern = pattern
        super().__init__("Prompt injection attempt detected and blocked")
