"""Embedding generation for the RAG knowledge base."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def get_embedding_function() -> Any:
    """Return an embedding function compatible with ChromaDB.

    Tries the following in order:
    1. ``chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction``
       (local, no API key needed).
    2. ``chromadb.utils.embedding_functions.OpenAIEmbeddingFunction``
       (requires ``OPENAI_API_KEY`` env var).
    3. ChromaDB's built-in default embedding function.

    Returns:
        A ChromaDB-compatible ``EmbeddingFunction`` instance.
    """
    # Attempt 1: sentence-transformers (local, free)
    try:
        from chromadb.utils.embedding_functions import (
            SentenceTransformerEmbeddingFunction,
        )

        ef = SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2",
        )
        logger.info("Using SentenceTransformer embeddings (all-MiniLM-L6-v2).")
        return ef
    except (ImportError, Exception) as exc:
        logger.debug("SentenceTransformer not available: %s", exc)

    # Attempt 2: OpenAI embeddings
    try:
        import os

        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

            ef = OpenAIEmbeddingFunction(
                api_key=api_key,
                model_name="text-embedding-3-small",
            )
            logger.info("Using OpenAI embeddings (text-embedding-3-small).")
            return ef
    except (ImportError, Exception) as exc:
        logger.debug("OpenAI embeddings not available: %s", exc)

    # Attempt 3: ChromaDB default
    try:
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

        ef = DefaultEmbeddingFunction()
        logger.info("Using ChromaDB default embedding function.")
        return ef
    except (ImportError, Exception) as exc:
        logger.debug("Default embedding function not available: %s", exc)

    logger.warning("No embedding function available — returning None (ChromaDB will use its built-in).")
    return None


def chunk_document(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> list[str]:
    """Split a document into overlapping chunks for embedding.

    Splits preferentially on paragraph boundaries (double newline), then
    sentence boundaries, falling back to hard character splits.

    Args:
        text: Full document text.
        chunk_size: Target size of each chunk in characters.
        chunk_overlap: Number of overlapping characters between consecutive chunks.

    Returns:
        List of text chunks.
    """
    if not text or not text.strip():
        return []

    if len(text) <= chunk_size:
        return [text.strip()]

    chunks: list[str] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)

        if end < text_len:
            # Try to break at a paragraph boundary
            para_break = text.rfind("\n\n", start, end)
            if para_break > start + chunk_size // 2:
                end = para_break + 2
            else:
                # Try sentence boundary
                for sep in (". ", ".\n", "? ", "!\n", ";\n"):
                    sent_break = text.rfind(sep, start, end)
                    if sent_break > start + chunk_size // 2:
                        end = sent_break + len(sep)
                        break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Advance with overlap
        start = max(start + 1, end - chunk_overlap)

    return chunks
