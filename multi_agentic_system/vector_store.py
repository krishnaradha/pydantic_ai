"""Document ingestion pipeline: load → chunk → embed → index in ChromaDB.

Example:
    ::

        builder = VectorStoreBuilder(settings)
        collection = await builder.build(docs_path="./docs")
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

from .config import FileType, Settings, get_logger
from .constants import CHROMA_TIMEOUT, EMBED_BATCH_SIZE, EMBED_TIMEOUT
from .exceptions import UnsupportedFileTypeError, VectorStoreError
from .utils.retry import retry_llm

if TYPE_CHECKING:
    from chromadb.api.models.Collection import Collection

logger = get_logger(__name__)

__all__ = ["VectorStoreBuilder"]


async def _run(timeout: float, fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a blocking callable in a thread with a hard timeout.

    Args:
        timeout: Maximum seconds to wait before raising ``asyncio.TimeoutError``.
        fn: Synchronous callable to execute.
        *args: Positional arguments forwarded to *fn*.
        **kwargs: Keyword arguments forwarded to *fn*.

    Returns:
        Return value of *fn*.

    Raises:
        asyncio.TimeoutError: If the call exceeds *timeout* seconds.
        VectorStoreError: Re-raised with context on any other exception.
    """
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(fn, *args, **kwargs), timeout=timeout
        )
    except asyncio.TimeoutError:
        raise
    except Exception as exc:
        raise VectorStoreError(str(exc)) from exc


class VectorStoreBuilder:
    """Loads documents from a directory, chunks them, and indexes in ChromaDB.

    On the first run the collection is built and persisted to ``cache_path``.
    Subsequent runs load directly from the persisted index with no re-embedding.

    Example:
        ::

            builder = VectorStoreBuilder(settings)
            collection = await builder.build("./docs", cache_path="./data/chroma")
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def build(
        self,
        docs_path: str | Path,
        cache_path: str | Path = "data/chroma",
    ) -> Collection:
        """Return a ChromaDB collection, loading from cache when available.

        Args:
            docs_path: Root directory to scan recursively for documents.
            cache_path: Directory where ChromaDB persists the index.

        Returns:
            A ready-to-query ChromaDB ``Collection``.

        Raises:
            DocumentNotFoundError: If no supported files exist on a cache miss.
            VectorStoreError: On unrecoverable ChromaDB failures.
            asyncio.TimeoutError: If a ChromaDB operation exceeds the timeout.
        """
        client: chromadb.ClientAPI = await _run(
            CHROMA_TIMEOUT, chromadb.PersistentClient, path=str(cache_path)
        )
        embedding_fn = OpenAIEmbeddingFunction(
            api_key=self._settings.openai_api_key.get_secret_value(),
            model_name=self._settings.embed_model,
        )

        existing = [c.name for c in await _run(CHROMA_TIMEOUT, client.list_collections)]
        if "docs" in existing:
            logger.info("Loading vector store from cache: %s", cache_path)
            return await _run(
                CHROMA_TIMEOUT, client.get_collection,
                name="docs", embedding_function=embedding_fn,
            )

        logger.info("Cache miss — building vector store from: %s", docs_path)
        root = Path(docs_path)
        files = sorted(
            f for f in root.rglob("*") if f.suffix.lower() in set(FileType)
        )
        if not files:
            logger.warning(
                "No .txt or .pdf files found under %s — starting with empty collection. "
                "Upload documents via POST /documents.",
                root.resolve(),
            )
            return await _run(
                CHROMA_TIMEOUT, client.create_collection,
                name="docs", embedding_function=embedding_fn,
            )

        ids, texts, metadatas = await self._ingest_files(files)
        logger.info("Indexed %d chunks from %d files.", len(ids), len(files))
        return await self._create_collection(client, embedding_fn, ids, texts, metadatas)

    async def _ingest_files(
        self, files: list[Path]
    ) -> tuple[list[str], list[str], list[dict[str, str | int]]]:
        """Load and chunk all files, returning parallel id/text/metadata lists.

        Args:
            files: Sorted list of document paths to ingest.

        Returns:
            A three-tuple of ``(ids, texts, metadatas)`` ready for ChromaDB.
        """
        ids: list[str] = []
        texts: list[str] = []
        metadatas: list[dict[str, str | int]] = []

        for file in files:
            logger.info("Loading %s", file.name)
            raw = await self._load_text(file)
            for i, chunk in enumerate(self._chunk_text(raw)):
                ids.append(f"{file.stem}_c{i}")
                texts.append(chunk)
                metadatas.append({"source": file.name, "chunk": i})

        return ids, texts, metadatas

    async def _load_text(self, path: Path) -> str:
        """Read raw text from a ``.txt`` or ``.pdf`` file.

        Args:
            path: Path to the document.

        Returns:
            Extracted plain text.

        Raises:
            UnsupportedFileTypeError: If the file extension is not supported.
        """
        match path.suffix.lower():
            case FileType.TXT:
                return await asyncio.to_thread(path.read_text, encoding="utf-8")
            case FileType.PDF:
                return await asyncio.to_thread(self._extract_pdf_text, path)
            case _:
                raise UnsupportedFileTypeError(path.suffix)

    @staticmethod
    def _extract_pdf_text(path: Path) -> str:
        """Extract plain text from a PDF using ``pypdf``.

        Args:
            path: Path to the PDF file.

        Returns:
            Concatenated page text.

        Raises:
            ImportError: If ``pypdf`` is not installed.
        """
        try:
            import pypdf  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "Install the pdf extra to load PDF files: uv sync --group pdf"
            ) from exc
        reader = pypdf.PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    def _chunk_text(self, text: str) -> list[str]:
        """Split text into overlapping fixed-size character chunks.

        Args:
            text: Raw document text.

        Returns:
            Non-empty text chunks.
        """
        chunk_size = self._settings.chunk_size
        step = chunk_size - self._settings.chunk_overlap
        start = 0
        chunks: list[str] = []
        while start < len(text):
            chunk = text[start : start + chunk_size]
            if chunk.strip():
                chunks.append(chunk)
            start += step
        return chunks

    @retry_llm
    async def _create_collection(
        self,
        client: chromadb.ClientAPI,
        embedding_fn: OpenAIEmbeddingFunction,
        ids: list[str],
        texts: list[str],
        metadatas: list[dict[str, str | int]],
    ) -> Collection:
        """Create a new persistent collection and populate it in batches.

        Decorated with :data:`~retry.retry_llm` to survive transient OpenAI
        embedding API errors.

        Args:
            client: ChromaDB persistent client.
            embedding_fn: OpenAI embedding function bound to the collection.
            ids: Unique chunk identifiers.
            texts: Chunk text content.
            metadatas: Per-chunk metadata dicts.

        Returns:
            The populated ChromaDB ``Collection``.
        """
        collection: Collection = await _run(
            CHROMA_TIMEOUT, client.create_collection,
            name="docs", embedding_function=embedding_fn,
        )
        for i in range(0, len(ids), EMBED_BATCH_SIZE):
            await _run(
                EMBED_TIMEOUT,
                collection.add,
                ids=ids[i : i + EMBED_BATCH_SIZE],
                documents=texts[i : i + EMBED_BATCH_SIZE],
                metadatas=metadatas[i : i + EMBED_BATCH_SIZE],
            )
        return collection
