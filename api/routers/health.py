"""Health router: ping all downstream services and report their status.

Endpoints
---------
GET /health
    Check OpenAI, Tavily, E2B, ChromaDB, and optionally Redis.
    Returns 200 when all required services are reachable, 503 otherwise.
"""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from multi_agentic_system import settings
from multi_agentic_system.config import get_logger

from ..schemas import HealthResponse, ServiceStatus

router = APIRouter()
logger = get_logger(__name__)

_PING_TIMEOUT = 10.0


async def _check(name: str, coro) -> ServiceStatus:
    """Run *coro* and return a :class:`~api.schemas.ServiceStatus`.

    Times the call and catches any exception as a failure.

    Args:
        name: Human-readable service label.
        coro: Awaitable that raises on failure or returns normally on success.

    Returns:
        :class:`~api.schemas.ServiceStatus` with latency or error details.
    """
    started = time.monotonic()
    try:
        await asyncio.wait_for(coro, timeout=_PING_TIMEOUT)
        latency = (time.monotonic() - started) * 1000
        return ServiceStatus(name=name, ok=True, latency_ms=round(latency, 2))
    except Exception as exc:
        latency = (time.monotonic() - started) * 1000
        logger.warning("Health check failed [%s]: %s", name, exc)
        return ServiceStatus(name=name, ok=False, latency_ms=round(latency, 2), error=str(exc))


async def _ping_openai() -> None:
    import openai  # noqa: PLC0415
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
    await client.models.list()


async def _ping_tavily(request: Request) -> None:
    tavily = request.app.state.tavily
    await asyncio.to_thread(
        tavily.search,
        query="health check ping",
        max_results=1,
    )


async def _ping_chroma(request: Request) -> None:
    collection = request.app.state.collection
    await asyncio.to_thread(collection.count)


async def _ping_e2b() -> None:
    from e2b_code_interpreter import Sandbox  # noqa: PLC0415
    sandbox = await asyncio.to_thread(Sandbox.create)
    await asyncio.to_thread(sandbox.kill)


async def _ping_redis(request: Request) -> None:
    store = request.app.state.history_store
    from multi_agentic_system.history_store import RedisHistoryStore  # noqa: PLC0415
    if not isinstance(store, RedisHistoryStore):
        raise RuntimeError("Redis not configured")
    client = store._assert_connected()
    await client.ping()


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=HealthResponse,
    summary="Service health check",
)
async def health_check(request: Request) -> JSONResponse:
    """Ping all downstream services and return their individual status.

    Required services (OpenAI, ChromaDB) failing will set ``healthy: false``
    and return HTTP 503. Optional services (Tavily, E2B, Redis) are reported
    but do not affect the top-level ``healthy`` flag.

    Args:
        request: FastAPI request — used to access ``app.state``.

    Returns:
        :class:`~api.schemas.HealthResponse` with per-service latency and
        error details. HTTP 200 when healthy, 503 when a required service
        is down.
    """
    results = await asyncio.gather(
        _check("openai",  _ping_openai()),
        _check("chromadb", _ping_chroma(request)),
        _check("tavily",  _ping_tavily(request)),
        _check("e2b",     _ping_e2b()),
    )
    services: list[ServiceStatus] = list(results)

    # Redis is optional — only checked when configured
    store = request.app.state.history_store
    from multi_agentic_system.history_store import RedisHistoryStore  # noqa: PLC0415
    if isinstance(store, RedisHistoryStore):
        redis_status = await _check("redis", _ping_redis(request))
        services.append(redis_status)

    required = {"openai", "chromadb"}
    healthy = all(s.ok for s in services if s.name in required)

    response = HealthResponse(healthy=healthy, services=services)
    http_status = status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(content=response.model_dump(), status_code=http_status)
