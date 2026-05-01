"""Documents router: upload and ingest new documents into the vector store.

Endpoints
---------
POST /documents
    Accept a ``.txt`` or ``.pdf`` file upload, persist it to ``docs/``,
    and add its chunks to the live ChromaDB collection.

GET /documents
    List all documents currently in the ``docs/`` directory.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile, status
from fastapi import File as FastAPIFile

from multi_agentic_system import settings
from multi_agentic_system.config import FileType, get_logger
from multi_agentic_system.exceptions import UnsupportedFileTypeError, VectorStoreError
from multi_agentic_system.vector_store import VectorStoreBuilder

from ..schemas import DocumentUploadResponse

router = APIRouter()
logger = get_logger(__name__)

_DOCS_DIR = Path("docs")
_MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB


def _assert_supported(filename: str) -> str:
    """Return the lowercased suffix or raise ``UnsupportedFileTypeError``.

    Args:
        filename: Original filename from the upload.

    Returns:
        Lowercased file extension, e.g. ``".pdf"``.

    Raises:
        UnsupportedFileTypeError: If the extension is not in :class:`~multi_agentic_system.config.FileType`.
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in set(FileType):
        raise UnsupportedFileTypeError(suffix)
    return suffix


async def _read_limited(upload: UploadFile) -> bytes:
    """Read upload bytes up to ``_MAX_FILE_BYTES``.

    Args:
        upload: FastAPI upload file object.

    Returns:
        Raw file bytes.

    Raises:
        HTTPException 413: If the file exceeds the size limit.
    """
    data = await upload.read(_MAX_FILE_BYTES + 1)
    if len(data) > _MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum allowed size is {_MAX_FILE_BYTES // 1024 // 1024} MB.",
        )
    return data


# ---------------------------------------------------------------------------
# POST /documents
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=DocumentUploadResponse,
    summary="Upload and ingest a document",
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    request: Request,
    file: UploadFile = FastAPIFile(..., description="A .txt or .pdf file to ingest"),
) -> DocumentUploadResponse:
    """Persist an uploaded file to ``docs/`` and add its chunks to the vector store.

    The file is written to ``docs/<filename>`` (overwriting if it exists), then
    chunked, embedded, and upserted into the live ChromaDB collection so queries
    immediately benefit from the new content without a server restart.

    Args:
        request: FastAPI request — used to access ``app.state.collection``.
        file: Multipart file upload.

    Returns:
        :class:`~api.schemas.DocumentUploadResponse` with the chunk count.

    Raises:
        400: If the file type is not supported.
        413: If the file exceeds 20 MB.
        500: On vector store ingestion failure.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file has no filename.",
        )

    try:
        _assert_supported(file.filename)
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    raw_bytes = await _read_limited(file)

    _DOCS_DIR.mkdir(parents=True, exist_ok=True)
    dest = _DOCS_DIR / file.filename
    await asyncio.to_thread(dest.write_bytes, raw_bytes)
    logger.info("Uploaded document saved: %s (%d bytes)", dest, len(raw_bytes))

    builder = VectorStoreBuilder(settings)

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / file.filename
            tmp_path.write_bytes(raw_bytes)

            ids, texts, metadatas = await builder._ingest_files([tmp_path])

        collection = request.app.state.collection
        await asyncio.to_thread(
            collection.upsert,
            ids=ids,
            documents=texts,
            metadatas=metadatas,
        )
    except VectorStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failed: {exc}",
        )

    logger.info("Ingested %d chunks from %s", len(ids), file.filename)
    return DocumentUploadResponse(
        filename=file.filename,
        chunks_added=len(ids),
        message=f"Successfully ingested {len(ids)} chunks from '{file.filename}'.",
    )


# ---------------------------------------------------------------------------
# GET /documents
# ---------------------------------------------------------------------------

@router.get(
    "",
    summary="List documents in the knowledge base",
    status_code=status.HTTP_200_OK,
)
async def list_documents() -> list[dict[str, object]]:
    """Return metadata for all documents currently in ``docs/``.

    Returns:
        List of dicts with ``filename``, ``size_bytes``, and ``suffix`` for
        each supported document file found in the ``docs/`` directory.
    """
    _DOCS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(
        f for f in _DOCS_DIR.rglob("*")
        if f.is_file() and f.suffix.lower() in set(FileType)
    )
    return [
        {
            "filename": f.name,
            "size_bytes": f.stat().st_size,
            "suffix": f.suffix.lower(),
        }
        for f in files
    ]
