# ── Stage 1: build deps with uv ───────────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency manifests first for layer caching
COPY pyproject.toml uv.lock ./

# Install all dependencies including optional groups used in production
RUN uv sync --frozen --no-install-project --group redis --group pdf

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

WORKDIR /app

# Non-root user for security
RUN addgroup --system app && adduser --system --ingroup app app

# Copy venv from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application source
COPY multi_agentic_system ./multi_agentic_system
COPY api ./api

# Persistent volume mount points
RUN mkdir -p data/chroma data/traces docs && chown -R app:app /app

USER app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
