"""Configuration, logging, and validated settings for the multi-agent system.

All secrets are loaded from environment variables (or a .env file) and
validated at startup via pydantic-settings. Missing or malformed keys raise
a clear ``ValidationError`` before any agent runs.

Logging is configured once here via :func:`get_logger`; every module obtains
its logger through that function so the Rich handler is applied consistently.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from rich.console import Console
from rich.logging import RichHandler

load_dotenv(Path(__file__).parents[1] / ".env")

__all__ = [
    "configure_logging",
    "get_logger",
    "console",
    "FileType",
    "LLMModel",
    "EmbedModel",
    "Settings",
    "settings",
]

console = Console(stderr=False)


def configure_logging(level: int = logging.INFO) -> None:
    """Configure root logging with a Rich handler (call once at startup).

    Args:
        level: Root log level, e.g. ``logging.DEBUG`` or ``logging.INFO``.
    """
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                console=console,
                rich_tracebacks=True,
                tracebacks_show_locals=True,
                show_path=False,
            )
        ],
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger that inherits the Rich root handler.

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        A :class:`logging.Logger` propagating to the Rich root handler.
    """
    return logging.getLogger(name)


class FileType(StrEnum):
    """Document file types supported by the vector-store ingestion pipeline."""

    TXT = ".txt"
    PDF = ".pdf"


class LLMModel(StrEnum):
    """Pydantic-AI model identifiers available to agents."""

    GPT4O = "openai:gpt-4o"
    GPT4O_MINI = "openai:gpt-4o-mini"


class EmbedModel(StrEnum):
    """OpenAI embedding model identifiers."""

    TEXT_EMBEDDING_3_SMALL = "text-embedding-3-small"
    TEXT_EMBEDDING_3_LARGE = "text-embedding-3-large"


class Settings(BaseSettings):
    """Application settings resolved from environment variables or a .env file.

    Secrets are stored as :class:`~pydantic.SecretStr` so they are redacted in
    logs and ``repr()`` output. Call ``.get_secret_value()`` only where the
    raw string is required (e.g. SDK constructors).

    ``e2b_api_key`` is required in ``.env`` and read directly from the
    environment by the E2B SDK — it does not need to be passed explicitly to
    ``Sandbox.create()``.

    Example:
        .env file::

            OPENAI_API_KEY=sk-...
            TAVILY_API_KEY=tvly-...
            E2B_API_KEY=e2b-...

    Attributes:
        openai_api_key: OpenAI secret key.
        tavily_api_key: Tavily search API key.
        e2b_api_key: E2B cloud sandbox API key (read by SDK from env automatically).
        logfire_token: Logfire project token. If omitted, Logfire runs in local-only mode.
        llm_model: Pydantic-AI model string used by all agents.
        embed_model: OpenAI embedding model name.
        chunk_size: Character width of each document chunk. Must be >= 10.
        chunk_overlap: Overlap between consecutive chunks. Must be < chunk_size.
        rag_top_k: Number of chunks returned per RAG query. Must be >= 1.
        web_search_top_k: Maximum Tavily results per search. Must be >= 1.
        code_agent_retries: Self-correction attempts allowed by the code agent. Must be >= 1.
        max_history_messages: Maximum messages retained in conversation history. Must be >= 1.
        tool_output_max_chars: Maximum characters of tool output fed back to the LLM.
        agent_timeout_seconds: Hard timeout for a single agent run in seconds.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    openai_api_key: SecretStr
    tavily_api_key: SecretStr
    e2b_api_key: SecretStr
    logfire_token: SecretStr | None = None

    llm_model: str = LLMModel.GPT4O
    embed_model: str = EmbedModel.TEXT_EMBEDDING_3_SMALL

    chunk_size: int = Field(default=400, ge=10)
    chunk_overlap: int = Field(default=80, ge=0)
    rag_top_k: int = Field(default=3, ge=1)
    web_search_top_k: int = Field(default=3, ge=1)
    code_agent_retries: int = Field(default=3, ge=1)
    max_history_messages: int = Field(default=20, ge=1)
    tool_output_max_chars: int = Field(default=8_000, ge=100)
    agent_timeout_seconds: float = Field(default=120.0, gt=0)

    @model_validator(mode="after")
    def overlap_less_than_chunk(self) -> Settings:
        """Ensure chunk_overlap is strictly less than chunk_size.

        Raises:
            ValueError: If ``chunk_overlap >= chunk_size``.

        Returns:
            The validated settings instance.
        """
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                f"chunk_overlap ({self.chunk_overlap}) must be less than "
                f"chunk_size ({self.chunk_size})"
            )
        return self


settings = Settings()  # type: ignore[call-arg]
