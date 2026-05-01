"""Main orchestrator agent: routes user queries to the appropriate tool.

Tools available to the agent:

- ``rag_search``        — semantic search over local documents (ChromaDB)
- ``web_search``        — live web search via Tavily
- ``summarize_content`` — delegates to :mod:`.summarize_agent`
- ``run_coding_task``   — delegates to :mod:`.code_agent` with an E2B sandbox
"""

from __future__ import annotations

import asyncio

from e2b_code_interpreter import Sandbox
from pydantic_ai import Agent, RunContext

from ..config import get_logger, settings
from ..constants import SANDBOX_TIMEOUT, SEARCH_TIMEOUT
from ..exceptions import AgentRunError, VectorStoreError
from ..models import AgentContext, CodeContext, SummarizeContext
from ..templates import render
from ..utils.retry import retry_transient
from ..utils.security import truncate_tool_output, validate_query
from .code_agent import code_agent
from .summarize_agent import summarize_agent

logger = get_logger(__name__)

assistant: Agent[AgentContext, str] = Agent(
    name="main_assistant",
    model=settings.llm_model,
    deps_type=AgentContext,
    output_type=str,
    retries=1,  # tool schema validation retries only — network retries handled by @retry_transient
)


@assistant.system_prompt
def _system_prompt(ctx: RunContext[AgentContext]) -> str:
    return render("main_agent.j2", user_id=ctx.deps.user_id)


@assistant.tool
@retry_transient
async def rag_search(ctx: RunContext[AgentContext], query: str) -> str:
    """Search the local document knowledge base using semantic similarity.

    Args:
        ctx: Run context; ``ctx.deps.chroma_collection`` is the vector store.
        query: Natural-language search query.

    Returns:
        Newline-separated passages prefixed with their source filename, or a
        fallback message if nothing was found.

    Raises:
        VectorStoreError: On unrecoverable ChromaDB failures.
    """
    safe_query = validate_query(query)
    logger.debug("[%s] RAG search: %s", ctx.deps.request_id, safe_query[:80])
    try:
        results = await asyncio.wait_for(
            asyncio.to_thread(
                ctx.deps.chroma_collection.query,
                query_texts=[safe_query],
                n_results=settings.rag_top_k,
            ),
            timeout=SEARCH_TIMEOUT,
        )
    except asyncio.TimeoutError as exc:
        raise VectorStoreError("ChromaDB query timed out") from exc

    passages = [
        f"[{meta['source']}] {text}"
        for text, meta in zip(results["documents"][0], results["metadatas"][0])
    ]
    output = "\n\n".join(passages) if passages else "No relevant documents found."
    return truncate_tool_output(output, settings.tool_output_max_chars)


@assistant.tool
@retry_transient
async def web_search(ctx: RunContext[AgentContext], query: str) -> str:
    """Search the web via Tavily when local docs are insufficient.

    Args:
        ctx: Run context; ``ctx.deps.tavily`` is the authenticated client.
        query: Natural-language search query.

    Returns:
        Newline-separated result snippets with titles, or a fallback message.
    """
    safe_query = validate_query(query)
    logger.debug("[%s] Web search: %s", ctx.deps.request_id, safe_query[:80])
    response = await asyncio.wait_for(
        asyncio.to_thread(
            ctx.deps.tavily.search,
            query=safe_query,
            max_results=settings.web_search_top_k,
        ),
        timeout=SEARCH_TIMEOUT,
    )
    results = response.get("results", [])
    if not results:
        return "No web results found."
    output = "\n\n".join(f"[{r['title']}] {r['content']}" for r in results)
    return truncate_tool_output(output, settings.tool_output_max_chars)


@assistant.tool
async def summarize_content(ctx: RunContext[AgentContext], text: str) -> str:
    """Condense a block of text using the dedicated summarise sub-agent.

    Args:
        ctx: Run context; ``ctx.deps`` is :class:`~..models.AgentContext`.
        text: The text to summarise.

    Returns:
        Bullet-point summary produced by the summarise sub-agent.

    Raises:
        AgentRunError: If the summarise sub-agent fails.
    """
    logger.debug("[%s] Delegating to summarize_agent", ctx.deps.request_id)
    safe_text = truncate_tool_output(text, settings.tool_output_max_chars)
    summarize_ctx = SummarizeContext.from_agent_context(ctx.deps, safe_text)
    try:
        result = await summarize_agent.run(
            "Please summarise the text provided in the system prompt.",
            deps=summarize_ctx,
        )
    except Exception as exc:
        raise AgentRunError("summarize_agent", exc) from exc
    return result.output


@assistant.tool
async def run_coding_task(ctx: RunContext[AgentContext], task: str) -> str:
    """Generate and verify Python code via the coding sub-agent and E2B sandbox.

    Args:
        ctx: Run context; ``ctx.deps`` is :class:`~..models.AgentContext`.
        task: Plain-English description of the coding task.

    Returns:
        Final working code and its stdout, produced by the code sub-agent.

    Raises:
        AgentRunError: If sandbox creation or the code sub-agent fails.
    """
    safe_task = validate_query(task)
    logger.debug("[%s] Delegating to code_agent: %s", ctx.deps.request_id, safe_task[:80])
    try:
        sandbox = await asyncio.wait_for(
            asyncio.to_thread(Sandbox.create), timeout=SANDBOX_TIMEOUT
        )
    except asyncio.TimeoutError as exc:
        raise AgentRunError("code_agent", exc) from exc
    except Exception as exc:
        raise AgentRunError("code_agent", exc) from exc

    try:
        code_ctx = CodeContext.from_agent_context(ctx.deps, safe_task, sandbox=sandbox)
        result = await code_agent.run(
            f"Complete this coding task: {safe_task}",
            deps=code_ctx,
        )
    except Exception as exc:
        raise AgentRunError("code_agent", exc) from exc
    finally:
        await asyncio.wait_for(
            asyncio.to_thread(sandbox.kill), timeout=SANDBOX_TIMEOUT
        )
    return result.output
