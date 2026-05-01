"""History router: read and clear per-user conversation history.

Endpoints
---------
GET  /history/{user_id}
    Return the stored message history for a user, optionally scoped to a session.

DELETE /history/{user_id}
    Clear the stored history for a user/session pair.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from multi_agentic_system.utils.security import validate_user_id
from multi_agentic_system.exceptions import InputTooLongError, PromptInjectionError
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from ..dependencies import HistoryStoreDep
from ..schemas import HistoryMessage, HistoryResponse

router = APIRouter()


def _flatten_messages(raw_messages: list) -> list[HistoryMessage]:
    """Convert pydantic-ai ``ModelMessage`` objects to flat role/content pairs.

    Only ``UserPromptPart`` and ``TextPart`` (LLM responses) are surfaced.
    Tool calls, system prompts, and tool results are omitted — they are
    internal plumbing not meaningful to a chat UI.

    Args:
        raw_messages: List of ``ModelRequest`` / ``ModelResponse`` objects.

    Returns:
        Ordered list of :class:`~api.schemas.HistoryMessage`, oldest first.
    """
    out: list[HistoryMessage] = []
    for message in raw_messages:
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, UserPromptPart):
                    out.append(HistoryMessage(role="user", content=str(part.content)))
        elif isinstance(message, ModelResponse):
            for part in message.parts:
                if isinstance(part, TextPart):
                    out.append(HistoryMessage(role="assistant", content=part.content))
    return out


# ---------------------------------------------------------------------------
# GET /history/{user_id}
# ---------------------------------------------------------------------------

@router.get(
    "/{user_id}",
    response_model=HistoryResponse,
    summary="Get conversation history for a user",
    status_code=status.HTTP_200_OK,
)
async def get_history(
    user_id: str,
    store: HistoryStoreDep,
    session_id: str = Query(default="default", min_length=1, max_length=128),
) -> HistoryResponse:
    """Return the flattened conversation history for *user_id* / *session_id*.

    Args:
        user_id: User identifier from the URL path.
        store: History store (injected).
        session_id: Optional session scope; defaults to ``"default"``.

    Returns:
        :class:`~api.schemas.HistoryResponse` with ordered user/assistant messages.

    Raises:
        400: If *user_id* fails validation.
        404: If no history exists for the given user/session pair.
    """
    try:
        safe_user = validate_user_id(user_id)
    except (InputTooLongError, PromptInjectionError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    raw = await store.get(f"{safe_user}:{session_id}")
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No history found for user '{safe_user}' session '{session_id}'",
        )

    return HistoryResponse(
        user_id=safe_user,
        session_id=session_id,
        messages=_flatten_messages(raw),
    )


# ---------------------------------------------------------------------------
# DELETE /history/{user_id}
# ---------------------------------------------------------------------------

@router.delete(
    "/{user_id}",
    summary="Clear conversation history for a user",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_history(
    user_id: str,
    store: HistoryStoreDep,
    session_id: str = Query(default="default", min_length=1, max_length=128),
) -> None:
    """Delete stored history for *user_id* / *session_id*.

    Always returns ``204`` — idempotent even if no history existed.

    Args:
        user_id: User identifier from the URL path.
        store: History store (injected).
        session_id: Optional session scope; defaults to ``"default"``.

    Raises:
        400: If *user_id* fails validation.
    """
    try:
        safe_user = validate_user_id(user_id)
    except (InputTooLongError, PromptInjectionError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    await store.delete(f"{safe_user}:{session_id}")
