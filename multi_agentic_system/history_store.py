"""Conversation history persistence with thread- and session-safe implementations.

Two implementations are provided:

- :class:`InMemoryHistoryStore` — per-process, async-safe via per-user locks.
  Suitable for single-process deployments and testing.
- :class:`RedisHistoryStore` — persistent across processes and restarts via Redis.
  Requires the ``redis`` extra (``uv sync --group redis``).

Both share the :class:`HistoryStore` protocol so they are interchangeable.

Example:
    ::

        store = RedisHistoryStore(url="redis://localhost:6379")
        await store.connect()

        history = await store.get(user_id)
        result  = await assistant.run(query, message_history=history or None, ...)
        await store.set(user_id, result.all_messages(), max_messages=20)

        await store.close()
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pydantic import ValidationError
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter

from .config import get_logger
from .constants import REDIS_KEY_PREFIX

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger(__name__)

__all__ = ["HistoryStore", "InMemoryHistoryStore", "RedisHistoryStore"]


@runtime_checkable
class HistoryStore(Protocol):
    """Async protocol for loading and persisting conversation history."""

    async def get(self, user_id: str) -> list[ModelMessage]:
        """Return the stored message history for *user_id*.

        Args:
            user_id: Unique identifier for the user or session.

        Returns:
            Ordered list of past messages, oldest first. Empty list if none stored.
        """
        ...

    async def set(
        self,
        user_id: str,
        messages: list[ModelMessage],
        max_messages: int,
    ) -> None:
        """Persist *messages* for *user_id*, trimming to the last *max_messages*.

        Args:
            user_id: Unique identifier for the user or session.
            messages: Full message list returned by ``result.all_messages()``.
            max_messages: Maximum number of messages to retain.
        """
        ...

    async def delete(self, user_id: str) -> None:
        """Remove all stored history for *user_id*.

        Args:
            user_id: Unique identifier for the user or session.
        """
        ...

    async def close(self) -> None:
        """Release any underlying connections or resources."""
        ...


def _serialise(messages: list[ModelMessage]) -> str:
    return ModelMessagesTypeAdapter.dump_json(messages).decode()


def _deserialise(raw: str) -> list[ModelMessage]:
    return ModelMessagesTypeAdapter.validate_json(raw)


def _trim(messages: list[ModelMessage], max_messages: int) -> list[ModelMessage]:
    """Trim to last *max_messages*, ensuring history starts at a clean turn boundary.

    History alternates: ModelRequest (user/tool-return) → ModelResponse (assistant).
    A naive tail-slice can orphan a ModelRequest that contains only ToolReturnParts
    (no UserPromptPart), because its preceding ModelResponse with tool_calls was
    sliced away. OpenAI rejects this with a 400: 'tool' message must follow
    'tool_calls'. We advance past any leading tool-only requests until we reach
    one that starts with a user prompt.
    """
    from pydantic_ai.messages import ModelRequest, UserPromptPart  # noqa: PLC0415

    trimmed = messages[-max_messages:]
    while trimmed:
        first = trimmed[0]
        if isinstance(first, ModelRequest) and any(
            isinstance(p, UserPromptPart) for p in first.parts
        ):
            break
        trimmed = trimmed[1:]
    return trimmed


class InMemoryHistoryStore:
    """Thread-safe in-process history store backed by a plain dict.

    Each user gets an individual :class:`asyncio.Lock` so concurrent coroutines
    operating on different users never contend, and concurrent coroutines for
    the same user serialise correctly.

    A module-level meta-lock guards the ``_locks`` dict itself, preventing a
    race condition where two coroutines simultaneously create different lock
    instances for the same user.
    """

    def __init__(self) -> None:
        self._store: dict[str, list[ModelMessage]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._meta_lock = asyncio.Lock()

    async def _lock(self, user_id: str) -> asyncio.Lock:
        async with self._meta_lock:
            if user_id not in self._locks:
                self._locks[user_id] = asyncio.Lock()
            return self._locks[user_id]

    async def get(self, user_id: str) -> list[ModelMessage]:
        lock = await self._lock(user_id)
        async with lock:
            return list(self._store.get(user_id, []))

    async def set(
        self,
        user_id: str,
        messages: list[ModelMessage],
        max_messages: int,
    ) -> None:
        lock = await self._lock(user_id)
        async with lock:
            self._store[user_id] = _trim(messages, max_messages)
            logger.debug(
                "History updated for %s: %d messages retained",
                user_id,
                len(self._store[user_id]),
            )

    async def delete(self, user_id: str) -> None:
        async with self._meta_lock:
            self._store.pop(user_id, None)
            self._locks.pop(user_id, None)

    async def close(self) -> None:
        pass


class RedisHistoryStore:
    """Persistent history store backed by Redis.

    Messages are serialised with pydantic-ai's ``ModelMessagesTypeAdapter`` and
    stored as a JSON string under the key ``chat_history:{user_id}``.

    Requires the ``redis`` extra::

        uv sync --group redis

    Attributes:
        _url: Redis connection URL.
        _client: Async Redis client, set after :meth:`connect` is called.
        _ttl: Optional key TTL in seconds. ``None`` means keys never expire.

    Example:
        ::

            store = RedisHistoryStore(url="redis://localhost:6379", ttl=86400)
            await store.connect()
    """

    _KEY_PREFIX = REDIS_KEY_PREFIX

    def __init__(self, url: str = "redis://localhost:6379", ttl: int | None = None) -> None:
        self._url = url
        self._ttl = ttl
        self._client: Redis[Any] | None = None

    async def connect(self) -> None:
        """Open the Redis connection pool and verify connectivity.

        Raises:
            ImportError: If the ``redis`` package is not installed.
            ConnectionError: If Redis is unreachable.
        """
        try:
            from redis.asyncio import Redis  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "Install the redis extra to use RedisHistoryStore: uv sync --group redis"
            ) from exc
        self._client = Redis.from_url(self._url, decode_responses=True)
        await self._client.ping()
        logger.info("RedisHistoryStore connected: %s", self._url)

    def _key(self, user_id: str) -> str:
        return f"{self._KEY_PREFIX}:{user_id}"

    def _assert_connected(self) -> Redis[Any]:
        if self._client is None:
            raise RuntimeError("RedisHistoryStore.connect() must be called before use.")
        return self._client

    async def get(self, user_id: str) -> list[ModelMessage]:
        client = self._assert_connected()
        raw: str | None = await client.get(self._key(user_id))
        if raw is None:
            return []
        try:
            return _deserialise(raw)
        except (ValidationError, ValueError) as exc:
            logger.warning("Corrupt history for %s, resetting: %s", user_id, exc)
            await self.delete(user_id)
            return []

    async def set(
        self,
        user_id: str,
        messages: list[ModelMessage],
        max_messages: int,
    ) -> None:
        client = self._assert_connected()
        trimmed = _trim(messages, max_messages)
        payload = _serialise(trimmed)
        if self._ttl:
            await client.setex(self._key(user_id), self._ttl, payload)
        else:
            await client.set(self._key(user_id), payload)
        logger.debug(
            "History persisted for %s: %d messages (ttl=%s)",
            user_id,
            len(trimmed),
            self._ttl,
        )

    async def delete(self, user_id: str) -> None:
        client = self._assert_connected()
        await client.delete(self._key(user_id))

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            logger.info("RedisHistoryStore connection closed")
