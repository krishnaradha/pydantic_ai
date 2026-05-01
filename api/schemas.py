"""Pydantic request and response models for the FastAPI layer.

These are the wire-format contracts between the frontend and the API.
They intentionally mirror :mod:`multi_agentic_system.result_schema` but are
decoupled so the API can evolve independently of the agent internals.

Schema hierarchy::

    QueryRequest  →  POST /query
    QueryResponse ←  POST /query  (wraps RunResult)

    StreamChunk   ←  POST /query/stream  (SSE token events)
    StreamDone    ←  POST /query/stream  (final SSE event)

    HistoryResponse  ←  GET /history/{user_id}

    TraceListResponse   ←  GET /traces
    TraceDetailResponse ←  GET /traces/{request_id}

    DocumentUploadResponse  ←  POST /documents

    HealthResponse  ←  GET /health
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    """Payload for a single agent query.

    Attributes:
        query: Natural-language question or instruction for the assistant.
        user_id: Caller identity; used to scope conversation history.
        session_id: Optional session scoping within a user. Defaults to
            ``"default"`` so callers that do not need multi-session can omit it.
    """

    query: str = Field(..., min_length=1, max_length=4_000)
    user_id: str = Field(..., min_length=1, max_length=128)
    session_id: str = Field(default="default", min_length=1, max_length=128)


class StateStepOut(BaseModel):
    """Wire representation of a single step in the agent state flow."""

    index: int
    step_type: str
    name: str | None
    content: str
    duration_ms: float | None


class TokenUsageOut(BaseModel):
    """Token counts returned to the frontend."""

    input_tokens: int
    output_tokens: int
    cached_tokens: int
    total_tokens: int


class CostBreakdownOut(BaseModel):
    """USD cost breakdown returned to the frontend."""

    input_cost_usd: float
    output_cost_usd: float
    cached_cost_usd: float
    total_cost_usd: float


class QueryResponse(BaseModel):
    """Full result of a completed agent run.

    Attributes:
        request_id: Correlation ID for log tracing.
        user_id: Echo of the requesting user.
        query: The validated query that was executed.
        timestamp: ISO-8601 UTC timestamp when the run started.
        model: Model string used, e.g. ``"openai:gpt-4o"``.
        status: One of ``success``, ``error``, ``timeout``, ``blocked``.
        final_output: Agent answer, or ``None`` on failure/block.
        response_time_ms: End-to-end wall-clock time.
        usage: Token counts.
        cost: Estimated USD cost.
        state_flow: Ordered execution trace.
        error: Error description when ``status != "success"``.
    """

    request_id: str
    user_id: str
    query: str
    timestamp: str
    model: str
    status: str
    final_output: str | None
    response_time_ms: float
    usage: TokenUsageOut
    cost: CostBreakdownOut
    state_flow: list[StateStepOut]
    error: str | None


# ---------------------------------------------------------------------------
# Streaming  (Server-Sent Events)
# ---------------------------------------------------------------------------

class StreamChunk(BaseModel):
    """A single streamed token chunk (SSE ``data:`` payload).

    Attributes:
        request_id: Correlation ID shared across all chunks for this run.
        delta: Partial token text from the model.
    """

    request_id: str
    delta: str


class StreamDone(BaseModel):
    """Terminal SSE event sent after all tokens; carries the full RunResult.

    Attributes:
        request_id: Correlation ID.
        result: Complete run result identical to :class:`QueryResponse`.
    """

    request_id: str
    result: QueryResponse


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

class HistoryMessage(BaseModel):
    """A single flattened message from the conversation history.

    Attributes:
        role: ``"user"`` or ``"assistant"``.
        content: Text content of the message.
    """

    role: str
    content: str


class HistoryResponse(BaseModel):
    """Conversation history for a user/session pair.

    Attributes:
        user_id: The requesting user.
        session_id: The session within that user.
        messages: Ordered list of prior messages, oldest first.
    """

    user_id: str
    session_id: str
    messages: list[HistoryMessage]


# ---------------------------------------------------------------------------
# Traces
# ---------------------------------------------------------------------------

class TraceSummary(BaseModel):
    """Lightweight trace entry for list views.

    Attributes:
        request_id: Correlation ID.
        user_id: Requesting user.
        query: Truncated query string (max 120 chars).
        timestamp: ISO-8601 UTC start time.
        status: Run outcome.
        response_time_ms: Wall-clock duration.
        total_tokens: Aggregate token count.
        total_cost_usd: Estimated USD cost.
    """

    request_id: str
    user_id: str
    query: str
    timestamp: str
    status: str
    response_time_ms: float
    total_tokens: int
    total_cost_usd: float


class TraceListResponse(BaseModel):
    """Paginated list of trace summaries.

    Attributes:
        date: Calendar date of the traces file (``YYYY-MM-DD``).
        total: Total number of traces on this date.
        traces: Page of trace summaries.
    """

    date: str
    total: int
    traces: list[TraceSummary]


class TraceDetailResponse(QueryResponse):
    """Full trace detail — identical to :class:`QueryResponse`."""


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

class DocumentUploadResponse(BaseModel):
    """Result of uploading and ingesting a document.

    Attributes:
        filename: Original uploaded filename.
        chunks_added: Number of chunks embedded into the vector store.
        message: Human-readable summary.
    """

    filename: str
    chunks_added: int
    message: str


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class ServiceStatus(BaseModel):
    """Status of a single downstream service.

    Attributes:
        name: Human-readable service name.
        ok: ``True`` if the ping succeeded.
        latency_ms: Round-trip time in milliseconds, or ``None`` if the check failed.
        error: Error string when ``ok`` is ``False``.
    """

    name: str
    ok: bool
    latency_ms: float | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    """Aggregate health of all downstream services.

    Attributes:
        healthy: ``True`` only when all required services are reachable.
        services: Individual status for each checked service.
    """

    healthy: bool
    services: list[ServiceStatus]
