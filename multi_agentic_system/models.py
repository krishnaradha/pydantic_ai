"""Dependency-injection contexts passed as ``deps=`` to every pydantic-ai agent.

Context hierarchy::

    AgentContext
        ├── SummarizeContext   (+ text_to_summarize)
        └── CodeContext        (+ task + live E2B sandbox)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import chromadb
from e2b_code_interpreter import Sandbox
from pydantic_ai.messages import ModelMessage
from tavily import TavilyClient

__all__ = ["AgentContext", "SummarizeContext", "CodeContext"]


@dataclass
class AgentContext:
    """Request-scoped state shared by the main agent and all its tools.

    Attributes:
        user_id: Identifier for the requesting user.
        chroma_collection: Pre-built ChromaDB collection used for RAG search.
        tavily: Authenticated Tavily client for live web search.
        history: Sliding window of recent conversation messages passed to each run.
        request_id: Unique ID for this request, propagated through all sub-agent calls
            for log correlation.
    """

    user_id: str
    chroma_collection: chromadb.Collection = field(repr=False)
    tavily: TavilyClient = field(repr=False)
    history: list[ModelMessage] = field(default_factory=list, repr=False)
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


@dataclass
class SummarizeContext(AgentContext):
    """Extends :class:`AgentContext` with the text the summarise agent should condense.

    Attributes:
        text_to_summarize: Raw text injected into the summarise agent's system prompt.
    """

    text_to_summarize: str = ""

    @classmethod
    def from_agent_context(cls, ctx: AgentContext, text: str) -> SummarizeContext:
        """Upgrade an :class:`AgentContext` into a :class:`SummarizeContext`.

        Args:
            ctx: Parent context whose shared fields are forwarded.
            text: The text to be summarised.

        Returns:
            A new :class:`SummarizeContext` ready to pass as ``deps=``.
        """
        return cls(
            user_id=ctx.user_id,
            chroma_collection=ctx.chroma_collection,
            tavily=ctx.tavily,
            history=ctx.history,
            request_id=ctx.request_id,
            text_to_summarize=text,
        )


@dataclass
class CodeContext(AgentContext):
    """Extends :class:`AgentContext` with a coding task and a live E2B sandbox.

    The sandbox is created once per ``run_coding_task`` call and reused across
    all ``execute_python`` tool invocations, giving true REPL behaviour where
    variables and imports persist between calls.

    Attributes:
        task: Plain-English description of the coding task.
        sandbox: Live E2B ``Sandbox`` instance with a persistent Python kernel.
    """

    task: str = ""
    sandbox: Sandbox = field(default=None, repr=False)  # type: ignore[assignment]
    execution_count: int = field(default=0, repr=False)

    @classmethod
    def from_agent_context(
        cls, ctx: AgentContext, task: str, sandbox: Sandbox
    ) -> CodeContext:
        """Upgrade an :class:`AgentContext` into a :class:`CodeContext`.

        Args:
            ctx: Parent context whose shared fields are forwarded.
            task: Plain-English coding task description.
            sandbox: Open E2B sandbox to reuse across ``execute_python`` calls.

        Returns:
            A new :class:`CodeContext` ready to pass as ``deps=``.
        """
        return cls(
            user_id=ctx.user_id,
            chroma_collection=ctx.chroma_collection,
            tavily=ctx.tavily,
            history=ctx.history,
            request_id=ctx.request_id,
            task=task,
            sandbox=sandbox,
        )
