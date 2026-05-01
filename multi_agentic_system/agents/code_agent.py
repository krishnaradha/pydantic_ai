"""Code sub-agent: generates, executes, and self-corrects Python via E2B.

Invoked exclusively from the ``run_coding_task`` tool on the main agent —
never called directly by users.

The LLM is instructed to follow this loop:

1. Write a complete, runnable Python script.
2. Call ``execute_python`` with that code.
3. Inspect the output; if correct, return final code and output.
4. If there is an error or wrong output, fix the code and retry.
5. Repeat up to ``MAX_TOOL_RETRIES`` times.
"""

from __future__ import annotations

import asyncio

from pydantic_ai import Agent, RunContext

from ..config import get_logger, settings
from ..constants import CODE_EXECUTION_TIMEOUT, MAX_TOOL_RETRIES
from ..exceptions import AgentRunError
from ..models import CodeContext
from ..templates import render

logger = get_logger(__name__)

code_agent: Agent[CodeContext, str] = Agent(
    name="code_agent",
    model=settings.llm_model,
    deps_type=CodeContext,
    output_type=str,
    retries=1,  # tool schema validation retries only — self-correction loop is prompt-driven
)


@code_agent.system_prompt
def _system_prompt(ctx: RunContext[CodeContext]) -> str:
    return render(
        "code_agent.j2",
        task=ctx.deps.task,
        retries=MAX_TOOL_RETRIES,
    )


@code_agent.tool
async def execute_python(ctx: RunContext[CodeContext], code: str) -> str:
    """Execute Python code inside the persistent E2B sandbox and return output.

    Variables and imports defined in previous calls remain available, giving
    true REPL behaviour. The full traceback is returned on failure so the agent
    can identify and fix the error before retrying.

    Args:
        ctx: Run context; ``ctx.deps.sandbox`` is the live E2B ``Sandbox``.
        code: Python source code to execute.

    Returns:
        stdout text on success, or a formatted error string on failure.
    """
    ctx.deps.execution_count += 1
    logger.debug(
        "[%s] Executing code in E2B sandbox (attempt %d/%d)",
        ctx.deps.request_id, ctx.deps.execution_count, MAX_TOOL_RETRIES,
    )

    if ctx.deps.execution_count > MAX_TOOL_RETRIES:
        return (
            f"LIMIT REACHED: execute_python has been called {MAX_TOOL_RETRIES} times. "
            "Stop now and return the best result you have so far."
        )

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(ctx.deps.sandbox.run_code, code),
            timeout=CODE_EXECUTION_TIMEOUT,
        )
    except asyncio.TimeoutError as exc:
        raise AgentRunError("code_agent", exc) from exc

    if result.error:
        logger.warning(
            "[%s] Sandbox execution error: %s",
            ctx.deps.request_id,
            result.error.name,
        )
        return (
            f"ERROR: {result.error.name}: {result.error.value}\n"
            f"{result.error.traceback}"
        )

    output = result.text or "(no output)"
    if ctx.deps.execution_count >= MAX_TOOL_RETRIES:
        return output + f"\n\n[Max executions ({MAX_TOOL_RETRIES}) reached — return this result now.]"
    return output
