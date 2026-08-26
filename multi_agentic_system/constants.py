"""Package-wide constants for the multi-agent system.

All magic numbers and limits live here. Import from this module rather than
defining inline values in individual modules.
"""

from __future__ import annotations

__all__ = [
    "MAX_QUERY_CHARS",
    "MAX_USER_ID_CHARS",
    "EMBED_BATCH_SIZE",
    "CHROMA_TIMEOUT",
    "EMBED_TIMEOUT",
    "SEARCH_TIMEOUT",
    "SANDBOX_TIMEOUT",
    "CODE_EXECUTION_TIMEOUT",
    "REDIS_KEY_PREFIX",
    "MAX_TOOL_RETRIES",
]

MAX_QUERY_CHARS: int = 4000
MAX_USER_ID_CHARS: int = 128

EMBED_BATCH_SIZE: int = 2000
CHROMA_TIMEOUT: float = 30.0
EMBED_TIMEOUT: float = 60.0

SEARCH_TIMEOUT: float = 15.0
SANDBOX_TIMEOUT: float = 30.0
CODE_EXECUTION_TIMEOUT: float = 60.0

REDIS_KEY_PREFIX: str = "chat_history"

MAX_TOOL_RETRIES: int = 5

MODEL_PRICING: dict[str, dict[str, float]] = {
    "openai:gpt-4o": {
        "input":  2.50 / 1_000_000,
        "output": 10.00 / 1_000_000,
        "cached": 1.25 / 1_000_000,
    },
    "openai:gpt-4o-mini": {
        "input":  0.150 / 1_000_000,
        "output": 0.600 / 1_000_000,
        "cached": 0.075 / 1_000_000,
    },
    "openai:gpt-4.1": {
        "input":  2.00 / 1_000_000,
        "output": 8.00 / 1_000_000,
        "cached": 0.50 / 1_000_000,
    },
    "openai:gpt-4.1-mini": {
        "input":  0.40 / 1_000_000,
        "output": 1.60 / 1_000_000,
        "cached": 0.10 / 1_000_000,
    },
}
