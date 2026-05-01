"""FastAPI application entry point.

Wires the lifespan, CORS middleware, and all routers into a single
application instance. Run with::

    uv run uvicorn api.main:app --reload --port 8000

Environment variables (in addition to those required by the agent core):

- ``CORS_ORIGINS`` — comma-separated list of allowed origins.
  Defaults to ``http://localhost:3000`` (Next.js dev server).
- ``REDIS_URL``    — optional Redis URL for persistent history.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from multi_agentic_system.config import configure_logging

from .dependencies import lifespan
from .routers import documents, health, history, query, traces

configure_logging()

_cors_origins = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

app = FastAPI(
    title="Multi-Agentic System API",
    description=(
        "REST + SSE interface to the pydantic-ai multi-agent system. "
        "Exposes query execution, conversation history, trace inspection, "
        "document ingestion, and service health."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query.router,     prefix="/query",     tags=["Query"])
app.include_router(history.router,   prefix="/history",   tags=["History"])
app.include_router(traces.router,    prefix="/traces",    tags=["Traces"])
app.include_router(documents.router, prefix="/documents", tags=["Documents"])
app.include_router(health.router,    prefix="/health",    tags=["Health"])


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"status": "ok", "docs": "/docs"}
