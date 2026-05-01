"""Traces router: inspect persisted run results.

Endpoints
---------
GET /traces
    Paginated list of trace summaries for a given date (defaults to today).

GET /traces/{request_id}
    Full detail for a single trace identified by its ``request_id``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status

from multi_agentic_system.observability import TraceStore
from multi_agentic_system.result_schema import RunResult

from ..dependencies import TraceStoreDep
from ..schemas import TraceDetailResponse, TraceListResponse, TraceSummary

router = APIRouter()


def _to_summary(r: RunResult) -> TraceSummary:
    return TraceSummary(
        request_id=r.request_id,
        user_id=r.user_id,
        query=r.query[:120] + ("…" if len(r.query) > 120 else ""),
        timestamp=r.timestamp,
        status=r.status,
        response_time_ms=r.response_time_ms,
        total_tokens=r.usage.total_tokens,
        total_cost_usd=r.cost.total_cost_usd,
    )


def _load_for_date(store: TraceStore, date: str) -> list[RunResult]:
    """Load traces for a specific ``YYYY-MM-DD`` date string.

    Falls back to today when *date* is ``"today"``.

    Args:
        store: The shared :class:`~multi_agentic_system.observability.TraceStore`.
        date: Calendar date string or the literal ``"today"``.

    Returns:
        All :class:`~multi_agentic_system.result_schema.RunResult` objects for that date.

    Raises:
        HTTPException 400: If *date* is not a valid ``YYYY-MM-DD`` string.
    """
    if date == "today":
        return store.load_today()

    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date '{date}'. Expected YYYY-MM-DD or 'today'.",
        )

    from pathlib import Path  # noqa: PLC0415
    import json  # noqa: PLC0415
    from multi_agentic_system.result_schema import CostBreakdown, StateStep, TokenUsage  # noqa: PLC0415

    path = Path(store._base_dir) / f"traces_{date}.jsonl"
    if not path.exists():
        return []

    results: list[RunResult] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            data["state_flow"] = [StateStep(**s) for s in data.get("state_flow", [])]
            data["usage"] = TokenUsage(**data.get("usage", {}))
            data["cost"] = CostBreakdown(**data.get("cost", {}))
            results.append(RunResult(**data))
    return results


# ---------------------------------------------------------------------------
# GET /traces
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=TraceListResponse,
    summary="List trace summaries",
    status_code=status.HTTP_200_OK,
)
async def list_traces(
    traces: TraceStoreDep,
    date: str = Query(default="today", description="YYYY-MM-DD or 'today'"),
    page: int = Query(default=1, ge=1, description="1-based page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Results per page"),
    status_filter: str | None = Query(default=None, alias="status", description="Filter by status"),
    user_id: str | None = Query(default=None, description="Filter by user_id"),
) -> TraceListResponse:
    """Return a paginated list of trace summaries for the requested date.

    Args:
        traces: Trace store (injected).
        date: Calendar date to load (``YYYY-MM-DD`` or ``"today"``).
        page: 1-based page number.
        page_size: Number of results per page (max 100).
        status_filter: Optional filter on ``status`` field.
        user_id: Optional filter on ``user_id`` field.

    Returns:
        :class:`~api.schemas.TraceListResponse` with pagination metadata and
        a page of :class:`~api.schemas.TraceSummary` objects, newest first.
    """
    all_results = _load_for_date(traces, date)

    if status_filter:
        all_results = [r for r in all_results if r.status == status_filter]
    if user_id:
        all_results = [r for r in all_results if r.user_id == user_id]

    all_results = list(reversed(all_results))

    total = len(all_results)
    start = (page - 1) * page_size
    page_results = all_results[start : start + page_size]

    effective_date = datetime.now(UTC).strftime("%Y-%m-%d") if date == "today" else date

    return TraceListResponse(
        date=effective_date,
        total=total,
        traces=[_to_summary(r) for r in page_results],
    )


# ---------------------------------------------------------------------------
# GET /traces/{request_id}
# ---------------------------------------------------------------------------

@router.get(
    "/{request_id}",
    response_model=TraceDetailResponse,
    summary="Get full detail for a single trace",
    status_code=status.HTTP_200_OK,
)
async def get_trace(
    request_id: str,
    traces: TraceStoreDep,
    date: str = Query(default="today", description="YYYY-MM-DD or 'today'"),
) -> TraceDetailResponse:
    """Return the full :class:`~api.schemas.TraceDetailResponse` for *request_id*.

    Args:
        request_id: The 12-character hex correlation ID.
        traces: Trace store (injected).
        date: Calendar date to search (``YYYY-MM-DD`` or ``"today"``).
            Cross-day lookups require the caller to pass the correct date.

    Returns:
        Full trace detail including state flow, token usage, and cost.

    Raises:
        404: If no trace with *request_id* exists on *date*.
    """
    all_results = _load_for_date(traces, date)
    match = next((r for r in all_results if r.request_id == request_id), None)

    if match is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trace '{request_id}' not found for date '{date}'.",
        )

    from dataclasses import asdict  # noqa: PLC0415
    return TraceDetailResponse(**asdict(match))
