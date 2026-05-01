"""Query router: non-streaming and SSE-streaming agent execution.

Endpoints
---------
POST /query
    Runs the agent to completion and returns the full :class:`~api.schemas.QueryResponse`.

POST /query/stream
    Streams token deltas as Server-Sent Events (``text/event-stream``).
    Each event carries a JSON-encoded :class:`~api.schemas.StreamChunk`.
    The final event carries a JSON-encoded :class:`~api.schemas.StreamDone`
    with the complete :class:`~api.schemas.QueryResponse`.

Both endpoints share the same security validation, history loading, and
trace persistence logic.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from multi_agentic_system import assistant, settings
from multi_agentic_system.exceptions import AgentSystemError, InputTooLongError, PromptInjectionError
from multi_agentic_system.observability import build_run_result
from multi_agentic_system.utils.security import validate_query, validate_user_id

from ..dependencies import ContextFactoryDep, HistoryStoreDep, TraceStoreDep
from ..schemas import QueryRequest, QueryResponse, StreamChunk, StreamDone

router = APIRouter()


def _to_response(run_result: object) -> QueryResponse:
    """Convert a :class:`~multi_agentic_system.result_schema.RunResult` to wire schema."""
    from multi_agentic_system.result_schema import RunResult  # noqa: PLC0415
    assert isinstance(run_result, RunResult)
    d = asdict(run_result)
    return QueryResponse(**d)


# ---------------------------------------------------------------------------
# POST /query  — blocking
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=QueryResponse,
    summary="Run an agent query (blocking)",
    status_code=status.HTTP_200_OK,
)
async def run_query(
    body: QueryRequest,
    ctx_factory: ContextFactoryDep,
    store: HistoryStoreDep,
    traces: TraceStoreDep,
) -> QueryResponse:
    """Execute a query against the assistant and return the full result.

    Args:
        body: Validated request body.
        ctx_factory: App-level context factory (injected).
        store: Conversation history store (injected).
        traces: Trace persistence store (injected).

    Returns:
        Full :class:`~api.schemas.QueryResponse` including state flow, token
        usage, cost, and the agent's final answer.

    Raises:
        422: If the query or user_id fail validation.
        400: If the query is blocked by security rules.
        504: If the agent exceeds ``agent_timeout_seconds``.
        500: On unrecoverable agent errors.
    """
    try:
        safe_user = validate_user_id(body.user_id)
        safe_query = validate_query(body.query)
    except (InputTooLongError, PromptInjectionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    ctx = ctx_factory.build(safe_user)
    ctx.history = await store.get(f"{safe_user}:{body.session_id}")
    started_at = time.monotonic()

    try:
        result = await asyncio.wait_for(
            assistant.run(
                safe_query,
                deps=ctx,
                message_history=ctx.history or None,
            ),
            timeout=settings.agent_timeout_seconds,
        )
    except asyncio.TimeoutError:
        run_result = build_run_result(
            ctx.request_id, safe_user, safe_query,
            model=settings.llm_model, started_at=started_at,
            status="timeout", error="Agent timed out",
        )
        await traces.save(run_result)
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Agent timed out")
    except AgentSystemError as exc:
        run_result = build_run_result(
            ctx.request_id, safe_user, safe_query,
            model=settings.llm_model, started_at=started_at,
            status="error", error=str(exc),
        )
        await traces.save(run_result)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    run_result = build_run_result(
        ctx.request_id, safe_user, safe_query,
        model=settings.llm_model, result=result, started_at=started_at,
    )
    await store.set(
        f"{safe_user}:{body.session_id}",
        result.all_messages(),
        settings.max_history_messages,
    )
    await traces.save(run_result)

    return _to_response(run_result)


# ---------------------------------------------------------------------------
# POST /query/stream  — Server-Sent Events
# ---------------------------------------------------------------------------

@router.post(
    "/stream",
    summary="Run an agent query (SSE streaming)",
    response_class=StreamingResponse,
)
async def stream_query(
    body: QueryRequest,
    ctx_factory: ContextFactoryDep,
    store: HistoryStoreDep,
    traces: TraceStoreDep,
) -> StreamingResponse:
    """Stream token deltas from the assistant as Server-Sent Events.

    Event format::

        data: {"request_id": "...", "delta": "partial text"}\\n\\n
        ...
        data: {"request_id": "...", "result": { <full QueryResponse> }}\\n\\n

    The last event has a ``result`` key instead of ``delta`` — the frontend
    should detect this to know the stream is complete and render final metrics.

    Args:
        body: Validated request body.
        ctx_factory: App-level context factory (injected).
        store: Conversation history store (injected).
        traces: Trace persistence store (injected).

    Returns:
        A ``text/event-stream`` :class:`~fastapi.responses.StreamingResponse`.

    Raises:
        400: If the query or user_id fail security validation (before streaming begins).
    """
    try:
        safe_user = validate_user_id(body.user_id)
        safe_query = validate_query(body.query)
    except (InputTooLongError, PromptInjectionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    ctx = ctx_factory.build(safe_user)
    ctx.history = await store.get(f"{safe_user}:{body.session_id}")

    return StreamingResponse(
        _sse_generator(body, safe_user, safe_query, ctx, store, traces),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _sse_generator(
    body: QueryRequest,
    safe_user: str,
    safe_query: str,
    ctx: object,
    store: HistoryStoreDep,
    traces: TraceStoreDep,
):
    """Async generator that yields SSE-formatted lines.

    Yields token ``StreamChunk`` events during the run, then a final
    ``StreamDone`` event with the complete result.
    """
    from multi_agentic_system.models import AgentContext  # noqa: PLC0415
    assert isinstance(ctx, AgentContext)

    started_at = time.monotonic()

    all_messages = None
    streamed_result = None
    stream_output: str | None = None

    try:
        async with assistant.run_stream(
            safe_query,
            deps=ctx,
            message_history=ctx.history or None,
        ) as streamed:
            async for delta in streamed.stream_text(delta=True):
                chunk = StreamChunk(request_id=ctx.request_id, delta=delta)
                yield f"data: {chunk.model_dump_json()}\n\n"

            # Must be captured inside the context manager while stream is open.
            # StreamedRunResult has no .output — get_data() returns the final str.
            stream_output = await streamed.get_data()
            all_messages = streamed.all_messages()
            streamed_result = streamed

    except asyncio.TimeoutError:
        run_result = build_run_result(
            ctx.request_id, safe_user, safe_query,
            model=settings.llm_model, started_at=started_at,
            status="timeout", error="Agent timed out",
        )
        await traces.save(run_result)
        yield f"data: {json.dumps({'request_id': ctx.request_id, 'error': 'timeout'})}\n\n"
        return
    except AgentSystemError as exc:
        run_result = build_run_result(
            ctx.request_id, safe_user, safe_query,
            model=settings.llm_model, started_at=started_at,
            status="error", error=str(exc),
        )
        await traces.save(run_result)
        yield f"data: {json.dumps({'request_id': ctx.request_id, 'error': str(exc)})}\n\n"
        return

    run_result = build_run_result(
        ctx.request_id, safe_user, safe_query,
        model=settings.llm_model, result=streamed_result, started_at=started_at,
        final_output=stream_output,
    )
    await store.set(
        f"{safe_user}:{body.session_id}",
        all_messages,
        settings.max_history_messages,
    )
    await traces.save(run_result)

    done = StreamDone(request_id=ctx.request_id, result=_to_response(run_result))
    yield f"data: {done.model_dump_json()}\n\n"
