"""Summarise sub-agent: condenses text into a concise bullet-point summary.

Invoked exclusively from the ``summarize_content`` tool on the main agent —
never called directly by users.
"""

from __future__ import annotations

from pydantic_ai import Agent, RunContext

from ..config import get_logger, settings
from ..models import SummarizeContext
from ..templates import render

logger = get_logger(__name__)

summarize_agent: Agent[SummarizeContext, str] = Agent(
    name="summarize_agent",
    model=settings.llm_model,
    deps_type=SummarizeContext,
    output_type=str,
)


@summarize_agent.system_prompt
def _system_prompt(ctx: RunContext[SummarizeContext]) -> str:
    return render("summarize_agent.j2", text=ctx.deps.text_to_summarize)
