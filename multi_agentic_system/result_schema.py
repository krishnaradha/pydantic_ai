"""Result schema for every agent request.

Each request produces exactly one :class:`RunResult` which captures the full
state flow, LLM token usage, cost breakdown, and timing. This is the canonical
object persisted to ``data/traces/`` and consumed by the frontend.

Schema hierarchy::

    RunResult
        ├── state_flow: list[StateStep]   (ordered execution trace)
        ├── usage: TokenUsage             (input / output / cached tokens)
        └── cost: CostBreakdown           (USD cost per token bucket)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum

from .constants import MODEL_PRICING

__all__ = [
    "StepType",
    "StateStep",
    "TokenUsage",
    "CostBreakdown",
    "RunResult",
]


class StepType(StrEnum):
    """Classifier for each step in the agent state flow."""

    USER_MESSAGE = "user_message"
    LLM_RESPONSE = "llm_response"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


@dataclass
class StateStep:
    """A single step in the agent's execution flow.

    Attributes:
        index: Zero-based position in the overall state flow.
        step_type: Classifier from :class:`StepType`.
        name: Tool name for ``TOOL_CALL`` / ``TOOL_RESULT`` steps; model name
            for ``LLM_RESPONSE``; ``None`` for ``USER_MESSAGE``.
        content: Truncated textual content of this step (max 500 chars).
        duration_ms: Wall-clock duration in milliseconds, or ``None`` if not
            measurable (e.g. user messages).
    """

    index: int
    step_type: str
    name: str | None
    content: str
    duration_ms: float | None


@dataclass
class TokenUsage:
    """LLM token counts for a single request.

    Attributes:
        input_tokens: Tokens in the request (prompt + history).
        output_tokens: Tokens in the model's response.
        cached_tokens: Prompt tokens served from the provider's cache.
        total_tokens: Sum of input and output tokens.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    total_tokens: int = 0


@dataclass
class CostBreakdown:
    """Estimated USD cost for a single request.

    Costs are derived from :data:`~constants.MODEL_PRICING`. If the model is
    not in the pricing table the cost fields are all ``0.0``.

    Attributes:
        input_cost_usd: Cost for input (prompt) tokens.
        output_cost_usd: Cost for output (completion) tokens.
        cached_cost_usd: Cost for cached prompt tokens (billed at a discount).
        total_cost_usd: Sum of all cost buckets.
    """

    input_cost_usd: float = 0.0
    output_cost_usd: float = 0.0
    cached_cost_usd: float = 0.0
    total_cost_usd: float = 0.0

    @classmethod
    def from_usage(cls, usage: TokenUsage, model: str) -> CostBreakdown:
        """Calculate cost from token counts and model pricing.

        Args:
            usage: Populated :class:`TokenUsage` for the request.
            model: Pydantic-AI model string, e.g. ``"openai:gpt-4o"``.

        Returns:
            A fully populated :class:`CostBreakdown`.
            All fields are ``0.0`` if *model* is not in the pricing table.
        """
        pricing = MODEL_PRICING.get(model)
        if not pricing:
            return cls()
        non_cached_input = max(usage.input_tokens - usage.cached_tokens, 0)
        input_cost = non_cached_input * pricing["input"]
        output_cost = usage.output_tokens * pricing["output"]
        cached_cost = usage.cached_tokens * pricing["cached"]
        return cls(
            input_cost_usd=round(input_cost, 8),
            output_cost_usd=round(output_cost, 8),
            cached_cost_usd=round(cached_cost, 8),
            total_cost_usd=round(input_cost + output_cost + cached_cost, 8),
        )


@dataclass
class RunResult:
    """Complete result snapshot for a single agent request.

    This is the top-level object saved to ``data/traces/`` as a JSON Lines
    entry and consumed by the Logfire dashboard and frontend.

    Attributes:
        request_id: Correlation ID propagated through the full call chain.
        user_id: Identifier of the requesting user.
        query: Validated user query string.
        timestamp: ISO-8601 UTC timestamp when the request started.
        model: Pydantic-AI model string used for this request.
        status: One of ``"success"``, ``"error"``, ``"timeout"``, ``"blocked"``.
        state_flow: Ordered list of execution steps from user message to final
            LLM response, including all tool calls and results.
        final_output: Agent's final text response, or ``None`` on failure.
        response_time_ms: End-to-end wall-clock time in milliseconds.
        usage: Token counts for this request.
        cost: Estimated USD cost derived from token counts and model pricing.
        error: Error description if ``status != "success"``, else ``None``.
    """

    request_id: str
    user_id: str
    query: str
    timestamp: str
    model: str
    status: str
    state_flow: list[StateStep] = field(default_factory=list)
    final_output: str | None = None
    response_time_ms: float = 0.0
    usage: TokenUsage = field(default_factory=TokenUsage)
    cost: CostBreakdown = field(default_factory=CostBreakdown)
    error: str | None = None

    def to_dict(self) -> dict:
        """Serialise to a JSON-safe dict.

        Returns:
            Nested dict representation suitable for ``json.dumps()``.
        """
        return asdict(self)
