# Multi-Agent System

A production-grade multi-agent AI system built on [pydantic-ai](https://ai.pydantic.dev). It routes user queries to specialised sub-agents via tool calls, exposes a streaming REST API, persists conversation history, and ships with a full Next.js dashboard — all containerised with Docker Compose.

---

## Architecture

```
 Browser
    │
    │ HTTP / SSE
    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              Docker Compose                                     │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                        webapp  :3000  (Next.js 14 / TypeScript)          │  │
│  │                                                                          │  │
│  │   /              Chat UI + Streaming      MetricsCard  StateFlowTable   │  │
│  │   /traces        Trace Explorer           Pagination   Detail Panel     │  │
│  │   /docs          Document Upload          Knowledge Base listing        │  │
│  │   /health        Service Health           Per-service latency           │  │
│  └───────────────────────────────┬──────────────────────────────────────────┘  │
│                                  │  REST + SSE                                 │
│                                  ▼                                              │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                         api  :8000  (FastAPI)                            │  │
│  │                                                                          │  │
│  │   POST /query            Blocking agent run → QueryResponse              │  │
│  │   POST /query/stream     SSE token stream → StreamChunk / StreamDone    │  │
│  │   GET  /history/{uid}    Conversation history (scoped per session)      │  │
│  │   DEL  /history/{uid}    Clear session history                          │  │
│  │   GET  /traces           Paginated RunResult list (filterable)          │  │
│  │   GET  /traces/{id}      Full RunResult detail + state flow             │  │
│  │   POST /documents        Upload .txt / .pdf → ingest into vector store  │  │
│  │   GET  /documents        List indexed documents                         │  │
│  │   GET  /health           Ping all downstream services                   │  │
│  │                                                                          │  │
│  │   Lifespan: boots ChromaDB collection, Tavily client, history store     │  │
│  └───────┬────────────────────────┬────────────────────┬────────────────────┘  │
│          │                        │                    │                        │
│          ▼                        ▼                    ▼                        │
│  ┌───────────────┐   ┌────────────────────┐   ┌──────────────┐                 │
│  │  redis  :6379 │   │  ChromaDB          │   │  TraceStore  │                 │
│  │               │   │  (named volume)    │   │  JSONL files │                 │
│  │  Conversation │   │  data/chroma/      │   │  data/traces/│                 │
│  │  history per  │   │                    │   │              │                 │
│  │  user+session │   │  docs/ embeddings  │   │  One file    │                 │
│  │               │   │  persisted across  │   │  per day     │                 │
│  │  RedisHistory │   │  restarts          │   │              │                 │
│  │  Store        │   │                    │   │              │                 │
│  └───────────────┘   └────────────────────┘   └──────────────┘                 │
│                                                                                 │
└──────────────────────────────────┬──────────────────────────────────────────────┘
                                   │
                                   │  Agent pipeline (per request)
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                          multi_agentic_system                                    │
│                                                                                  │
│   User query                                                                     │
│       │                                                                          │
│       ▼  security validation (prompt injection + shell command blocking)         │
│       │                                                                          │
│       ▼                                                                          │
│   assistant  (main orchestrator — gpt-4o / gpt-4o-mini)                         │
│       │                                                                          │
│       ├── rag_search ──────────────────► ChromaDB vector search                  │
│       │   @retry_transient                 returns top-k passages                │
│       │                                                                          │
│       ├── web_search ──────────────────► Tavily API                              │
│       │   @retry_transient                 returns live web snippets             │
│       │                                                                          │
│       ├── summarize_content ──────────► summarize_agent (sub-agent)              │
│       │                                   bullet-point summary                   │
│       │                                                                          │
│       └── run_coding_task ────────────► code_agent (sub-agent)                   │
│                                             │                                    │
│                                             └── execute_python ──► E2B Sandbox   │
│                                                  (max 5 runs,         cloud      │
│                                                   enforced in code)  execution   │
│                                                                                  │
│   Result ──► build_run_result() ──► RunResult (state_flow, tokens, cost, time)  │
│          ──► TraceStore.save()                                                   │
│          ──► HistoryStore.set()                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
                        │                      │                  │
              ┌─────────▼──────┐   ┌───────────▼──────┐  ┌───────▼────────┐
              │   OpenAI API   │   │   Tavily API     │  │   E2B API      │
              │  LLM + embed   │   │   web search     │  │  code sandbox  │
              └────────────────┘   └──────────────────┘  └────────────────┘
```

---

## Components

### webapp — Next.js 14 + TypeScript Frontend

The user-facing interface built with the App Router, shadcn/ui, TanStack Query, and Recharts.

| Page | Route | Description |
|---|---|---|
| Chat | `/` | Split-pane layout: streaming chat on the left, live metrics + state flow tabs on the right |
| Traces | `/traces` | Paginated trace list with status filter; click any row to inspect full RunResult detail |
| Docs | `/docs` | Upload `.txt` / `.pdf` files into the knowledge base; lists all indexed documents |
| Health | `/health` | Per-service ping status with latency; auto-refreshes every 30 seconds |

**Key files:**
- `lib/types.ts` — TypeScript interfaces mirroring FastAPI schemas exactly
- `lib/api.ts` — Axios client + native `fetch` SSE stream handler
- `components/ChatPanel.tsx` — streaming bubbles, thinking indicator, stop button
- `components/MetricsCard.tsx` — token bars, cost table, summary pills
- `components/StateFlowTable.tsx` — step-by-step execution trace

---

### api — FastAPI Backend

The REST + SSE layer that exposes the agent system. Boots all shared resources once at startup via the `lifespan` context manager.

**Startup sequence:**
1. `VectorStoreBuilder.build()` — loads ChromaDB from cache or builds from `docs/`
2. `TavilyClient` initialised with API key
3. `HistoryStore` selected — `RedisHistoryStore` if `REDIS_URL` is set, else `InMemoryHistoryStore`
4. `TraceStore` pointed at `data/traces/`

**Streaming (`POST /query/stream`):**
- Uses `assistant.run_stream()` from pydantic-ai
- Yields `StreamChunk` SSE events (token deltas) during the run
- Yields a final `StreamDone` event with the full `QueryResponse` including metrics
- History and traces saved after the stream completes

**Security:** every query passes through `validate_query()` before reaching the agent — blocks prompt injection patterns and Linux shell commands. `validate_user_id()` guards Redis key injection.

---

### multi_agentic_system — Agent Core

The pydantic-ai agent layer. Contains all agent definitions, tools, templates, and shared infrastructure.

#### assistant (main orchestrator)

The entry-point agent. Receives the validated query, decides which tool to call, and returns the final answer.

| Tool | Trigger | Backed by |
|---|---|---|
| `rag_search` | Answer likely in local docs | ChromaDB semantic search |
| `web_search` | External / current information | Tavily API |
| `summarize_content` | User asks for condensed text | `summarize_agent` sub-agent |
| `run_coding_task` | User asks to write / run code | `code_agent` + E2B sandbox |

#### summarize_agent (sub-agent)

Receives plain text via the `SummarizeContext` and returns a concise bullet-point summary. Invoked only from the `summarize_content` tool — never directly.

#### code_agent (sub-agent)

Generates, executes, and self-corrects Python code inside an E2B cloud sandbox.

- The sandbox is created once per `run_coding_task` call and reused across all `execute_python` invocations (REPL behaviour — variables persist between calls)
- Execution count is tracked in `CodeContext.execution_count` and enforced in code — the LLM cannot bypass the 5-call limit regardless of what it decides
- On the final allowed call the tool appends a hard-stop hint to the output

#### Observability pipeline

Every request — success, error, timeout, or blocked — produces a `RunResult`:

```
RunResult
├── state_flow: list[StateStep]    ordered execution trace (user → LLM → tool → result)
├── usage: TokenUsage              input / output / cached token counts
├── cost: CostBreakdown            USD cost per token bucket (from MODEL_PRICING table)
├── response_time_ms               end-to-end wall-clock time
└── status                         success | error | timeout | blocked
```

Results are:
- Appended as JSON Lines to `data/traces/traces_YYYY-MM-DD.jsonl` (one file per day)
- Optionally sent to [Logfire](https://logfire.pydantic.dev) for cloud tracing

---

### Redis — Conversation History

Stores conversation history per `user_id:session_id` key using pydantic-ai's `ModelMessagesTypeAdapter` for serialisation.

- `InMemoryHistoryStore` used when `REDIS_URL` is not set (single-process only)
- `RedisHistoryStore` used in Docker Compose (shared across all processes)
- History is a sliding window — oldest messages are trimmed to `max_history_messages`
- Supports full session scoping: one user can have multiple independent sessions

---

### ChromaDB — Vector Store

Persists document embeddings using OpenAI's `text-embedding-3-small` model.

- Documents are chunked into 400-character overlapping windows (80-char overlap)
- Embedding batched at 2000 chunks per call to stay within token limits
- Collection loaded from `data/chroma/` on startup — no re-embedding on restart
- New documents uploaded via `POST /documents` are upserted into the live collection without a restart

---

## Project Structure

```
pydantic_ai/
├── Dockerfile                        Backend container (multi-stage, uv)
├── docker-compose.yml                Orchestrates api + webapp + redis
├── pyproject.toml                    Python dependencies (grouped by concern)
├── .env                              Secrets (not committed)
│
├── api/                              FastAPI layer
│   ├── main.py                       App factory — CORS, lifespan, router mounts
│   ├── schemas.py                    Pydantic request / response models
│   ├── dependencies.py               Lifespan, Depends() providers, ContextFactory
│   └── routers/
│       ├── query.py                  POST /query, POST /query/stream
│       ├── history.py                GET / DELETE /history/{user_id}
│       ├── traces.py                 GET /traces, GET /traces/{request_id}
│       ├── documents.py              POST /documents, GET /documents
│       └── health.py                 GET /health
│
├── multi_agentic_system/             Agent core
│   ├── __init__.py                   Public API
│   ├── __main__.py                   CLI entry point (demo queries)
│   ├── config.py                     Settings, logging, console
│   ├── constants.py                  All magic numbers (timeouts, limits, pricing)
│   ├── exceptions.py                 Structured exception hierarchy
│   ├── models.py                     AgentContext, SummarizeContext, CodeContext
│   ├── result_schema.py              RunResult, StateStep, TokenUsage, CostBreakdown
│   ├── observability.py              Logfire, TraceStore, build_run_result, Rich dashboard
│   ├── history_store.py              InMemoryHistoryStore, RedisHistoryStore
│   ├── vector_store.py               VectorStoreBuilder — load → chunk → embed → index
│   ├── agents/
│   │   ├── main_agent.py             assistant — orchestrator with 4 tools
│   │   ├── summarize_agent.py        summarize_agent — bullet-point summaries
│   │   └── code_agent.py             code_agent — Python generation + E2B execution
│   ├── templates/
│   │   ├── main_agent.j2             System prompt for assistant
│   │   ├── summarize_agent.j2        System prompt for summarize_agent
│   │   └── code_agent.j2             System prompt for code_agent
│   └── utils/
│       ├── security.py               validate_query, validate_user_id, truncate_tool_output
│       └── retry.py                  retry_transient, retry_llm (tenacity decorators)
│
└── webapp/                           Next.js 14 frontend
    ├── Dockerfile                    Frontend container (multi-stage, standalone)
    ├── app/
    │   ├── layout.tsx                Root layout — NavBar, Providers
    │   ├── page.tsx                  Chat page
    │   ├── traces/page.tsx           Trace explorer
    │   ├── docs/page.tsx             Document management
    │   └── health/page.tsx           Health dashboard
    ├── components/
    │   ├── ChatPanel.tsx             Streaming chat UI
    │   ├── MetricsCard.tsx           Token bars, cost, timing
    │   ├── StateFlowTable.tsx        Step-by-step execution trace
    │   ├── HealthPanel.tsx           Per-service status
    │   └── NavBar.tsx                Top navigation
    └── lib/
        ├── types.ts                  TypeScript interfaces (mirrors FastAPI schemas)
        ├── api.ts                    Axios client + SSE stream handler
        └── providers.tsx             TanStack Query provider
```

---

## Security

| Layer | Mechanism |
|---|---|
| Query validation | Regex patterns block prompt injection, jailbreaks, and Linux shell commands |
| User ID validation | Alphanumeric + `_-.@` only — prevents Redis key injection |
| Tool output truncation | Caps tool results at `tool_output_max_chars` to prevent context overflow |
| Code execution limit | `execution_count` enforced in Python — LLM cannot bypass the 5-call cap |
| Non-root containers | Both api and webapp run as a non-root `app` user |
| Secrets | All API keys stored as `SecretStr` — redacted in logs and `repr()` |

---

## Running

### Docker (recommended)

```bash
cp .env.example .env          # fill in API keys
docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |

### Local development

```bash
# Backend
uv sync --group redis --group pdf
uv run uvicorn api.main:app --reload --port 8000

# Frontend
cd webapp && npm install && npm run dev
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | LLM inference and document embeddings |
| `TAVILY_API_KEY` | Yes | Live web search |
| `E2B_API_KEY` | Yes | Cloud Python sandbox for code execution |
| `LOGFIRE_TOKEN` | No | Logfire cloud tracing (local-only if omitted) |
| `LLM_MODEL` | No | Model string, e.g. `openai:gpt-4o` (default: `openai:gpt-4o`) |
| `REDIS_URL` | No | Redis connection URL (in-memory history if omitted) |
| `CORS_ORIGINS` | No | Comma-separated allowed origins (default: `http://localhost:3000`) |
| `NEXT_PUBLIC_API_URL` | No | API base URL baked into the frontend build (default: `http://localhost:8000`) |

---

## AWS Deployment

A $0 (free-tier) deployment — one EC2 instance, images built by CI/CD and
pulled from ECR, exposed directly via the instance's Elastic IP. Full
design rationale: [docs/aws-architecture.md](docs/aws-architecture.md).

**Setting this up from scratch in your own AWS account?** Start at
[END_TO_END_SETUP.md](END_TO_END_SETUP.md) — the complete, linear,
copy-paste path from `git clone` to a live deployment.

**First-time setup**, from an empty AWS account — explained step by step in
[docs/tutorials/aws/](docs/tutorials/aws/README.md), or automated as scripts:

```bash
# 1. Create every AWS resource (IAM, ECR, security group, EC2, Elastic IP, S3)
export AWS_REGION=ap-south-1
./scripts/aws-create-resources.sh

# 2. Set real application secrets (the script above can't know these)
aws ssm put-parameter --region $AWS_REGION --name /multi-agentic/OPENAI_API_KEY --type SecureString --value "sk-..."
aws ssm put-parameter --region $AWS_REGION --name /multi-agentic/TAVILY_API_KEY --type SecureString --value "tvly-..."
aws ssm put-parameter --region $AWS_REGION --name /multi-agentic/E2B_API_KEY --type SecureString --value "e2b_..."

# 3. Wire CI/CD to AWS and push the deploy files onto the instance
export EC2_INSTANCE_ID=... ECR_REGISTRY=... PUBLIC_API_URL=... \
       AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... GITHUB_REPO=owner/repo
./scripts/aws-integrate.sh

# 4. Ship it
git push origin main
```

Each script prints the env vars the next one needs — see their header
comments, or the tutorials, for the full list and what each one does.

**Day to day**, once it's set up:

| Script | Purpose |
|---|---|
| [scripts/aws-up.sh](scripts/aws-up.sh) | Start the EC2 instance back up after stopping it, and make sure containers are running |
| `aws ec2 stop-instances --instance-ids <id>` | Stop the instance to pause billing between uses |
| `git push origin main` | Redeploy — GitHub Actions builds, pushes to ECR, and deploys automatically |

See [docs/tutorials/aws/integration/end-to-end-setup.md](docs/tutorials/aws/integration/end-to-end-setup.md)
for a troubleshooting table of every real failure hit building this pipeline.
