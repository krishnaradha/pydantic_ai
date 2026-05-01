"""FastAPI dependency-injection providers and application lifespan.

On startup the lifespan:

1. Boots the vector store (loads from ChromaDB cache or rebuilds from docs/).
2. Creates the history store (in-memory by default; Redis if ``REDIS_URL`` is set).
3. Instantiates the Tavily client.
4. Stores all shared objects in ``app.state`` so every request can access them
   via the ``Depends()`` functions defined here.

On shutdown the lifespan closes the history store connection.

Usage in routers::

    from .dependencies import get_context_factory, get_history_store, get_trace_store

    @router.post("/query")
    async def query(
        body: QueryRequest,
        ctx_factory: ContextFactory = Depends(get_context_factory),
        store: HistoryStore = Depends(get_history_store),
        traces: TraceStore = Depends(get_trace_store),
    ):
        ...
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from tavily import TavilyClient

from multi_agentic_system import VectorStoreBuilder, settings
from multi_agentic_system.history_store import HistoryStore, InMemoryHistoryStore
from multi_agentic_system.models import AgentContext
from multi_agentic_system.observability import TraceStore, configure_logfire

__all__ = [
    "lifespan",
    "get_context_factory",
    "get_history_store",
    "get_trace_store",
    "ContextFactory",
]


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build shared resources once at startup and tear them down at shutdown.

    Sets ``app.state.collection``, ``app.state.tavily``,
    ``app.state.history_store``, and ``app.state.trace_store``.

    Args:
        app: The FastAPI application instance.

    Yields:
        Control to the running application.
    """
    configure_logfire(settings)

    builder = VectorStoreBuilder(settings)
    docs_path = Path("docs")
    docs_path.mkdir(parents=True, exist_ok=True)
    collection = await builder.build(
        docs_path=docs_path,
        cache_path=Path("data/chroma"),
    )

    tavily = TavilyClient(api_key=settings.tavily_api_key.get_secret_value())

    history_store: HistoryStore = await _build_history_store()

    trace_store = TraceStore(base_dir="data/traces")

    app.state.collection = collection
    app.state.tavily = tavily
    app.state.history_store = history_store
    app.state.trace_store = trace_store

    yield

    await history_store.close()


async def _build_history_store() -> HistoryStore:
    """Return a Redis-backed store when ``REDIS_URL`` is configured, else in-memory."""
    import os  # noqa: PLC0415
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        from multi_agentic_system.history_store import RedisHistoryStore  # noqa: PLC0415
        store = RedisHistoryStore(url=redis_url)
        await store.connect()
        return store
    return InMemoryHistoryStore()


# ---------------------------------------------------------------------------
# Typed factory
# ---------------------------------------------------------------------------

class ContextFactory:
    """Callable that builds a fresh :class:`AgentContext` for each request.

    The ``chroma_collection`` and ``tavily`` client are long-lived objects
    shared from ``app.state``; only the per-request fields (``user_id``,
    ``history``, ``request_id``) vary.

    Args:
        collection: ChromaDB collection from app state.
        tavily: Authenticated Tavily client from app state.
    """

    def __init__(self, collection: object, tavily: TavilyClient) -> None:
        self._collection = collection
        self._tavily = tavily

    def build(self, user_id: str) -> AgentContext:
        """Instantiate a new :class:`AgentContext` for *user_id*.

        Args:
            user_id: Validated user identifier from the request body.

        Returns:
            A fresh :class:`AgentContext` with a new ``request_id``.
        """
        return AgentContext(
            user_id=user_id,
            chroma_collection=self._collection,  # type: ignore[arg-type]
            tavily=self._tavily,
        )


# ---------------------------------------------------------------------------
# Depends providers
# ---------------------------------------------------------------------------

def get_context_factory(request: Request) -> ContextFactory:
    """FastAPI dependency that returns the shared :class:`ContextFactory`.

    Args:
        request: Injected by FastAPI.

    Returns:
        A :class:`ContextFactory` bound to the app-level ChromaDB collection
        and Tavily client.
    """
    return ContextFactory(
        collection=request.app.state.collection,
        tavily=request.app.state.tavily,
    )


def get_history_store(request: Request) -> HistoryStore:
    """FastAPI dependency that returns the shared :class:`HistoryStore`.

    Args:
        request: Injected by FastAPI.

    Returns:
        The app-level ``HistoryStore`` instance.
    """
    return request.app.state.history_store


def get_trace_store(request: Request) -> TraceStore:
    """FastAPI dependency that returns the shared :class:`TraceStore`.

    Args:
        request: Injected by FastAPI.

    Returns:
        The app-level ``TraceStore`` instance.
    """
    return request.app.state.trace_store


# ---------------------------------------------------------------------------
# Annotated shorthands for routers
# ---------------------------------------------------------------------------

ContextFactoryDep = Annotated[ContextFactory, Depends(get_context_factory)]
HistoryStoreDep   = Annotated[HistoryStore,   Depends(get_history_store)]
TraceStoreDep     = Annotated[TraceStore,     Depends(get_trace_store)]
