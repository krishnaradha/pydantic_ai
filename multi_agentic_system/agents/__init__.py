"""Pydantic-AI agent definitions for the multi-agent system.

Import order matters — tools are registered via decorators at module load time,
so each agent module must be imported before it is used.
"""

from .code_agent import code_agent
from .main_agent import assistant
from .summarize_agent import summarize_agent

__all__ = ["assistant", "code_agent", "summarize_agent"]
