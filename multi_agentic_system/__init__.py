"""Multi-agent system built on pydantic-ai.

Public API::

    from pydantic_ai.multi_agentic_system import assistant, settings, AgentContext
    from pydantic_ai.multi_agentic_system import VectorStoreBuilder

Architecture::

    docs/ folder
        └─► VectorStoreBuilder.build()   (chunks + embeds at startup)
                └─► ChromaDB in-memory collection
                        │
    User query          │
        └─► assistant (decides)
                ├─► rag_search tool          (queries ChromaDB)
                ├─► web_search tool          (Tavily)
                ├─► summarize_content tool
                │       └─► summarize_agent  (sub-agent)
                └─► run_coding_task tool
                        └─► code_agent       (sub-agent)
                                └─► execute_python tool
                                        └─► E2B cloud sandbox
"""

from .agents import assistant, code_agent, summarize_agent
from .config import Settings, settings
from .observability import TraceStore
from .result_schema import CostBreakdown, RunResult, StateStep, TokenUsage
from .exceptions import (
    AgentRunError,
    AgentSystemError,
    DocumentNotFoundError,
    InputTooLongError,
    PromptInjectionError,
    UnsupportedFileTypeError,
    VectorStoreError,
)
from .models import AgentContext, CodeContext, SummarizeContext
from .vector_store import VectorStoreBuilder

__all__ = [
    "assistant",
    "code_agent",
    "summarize_agent",
    "settings",
    "Settings",
    "AgentContext",
    "SummarizeContext",
    "CodeContext",
    "VectorStoreBuilder",
    "TraceStore",
    "RunResult",
    "StateStep",
    "TokenUsage",
    "CostBreakdown",
    "AgentSystemError",
    "AgentRunError",
    "DocumentNotFoundError",
    "InputTooLongError",
    "PromptInjectionError",
    "UnsupportedFileTypeError",
    "VectorStoreError",
]
