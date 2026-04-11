"""ChromaDB-backed RAG knowledge base for UiPath code generation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class Document(BaseModel):
    """A retrieved document chunk from the knowledge base."""

    content: str
    """Text content of the chunk."""
    source: str
    """Original file path or identifier."""
    metadata: dict[str, Any] = Field(default_factory=dict)
    """Arbitrary metadata (section, language, tags, etc.)."""
    score: float = 0.0
    """Similarity score (lower distance = better match in ChromaDB)."""


class KnowledgeBase:
    """Vector-store backed knowledge base using ChromaDB.

    Indexes Markdown, C#, and JSON files from a knowledge directory and
    supports semantic search via embeddings.
    """

    # File extensions to index
    INDEXABLE_EXTENSIONS: set[str] = {".md", ".cs", ".json"}

    def __init__(
        self,
        persist_dir: Path | str = ".rag_store",
        collection_name: str = "rpa_knowledge",
    ) -> None:
        """Initialise the knowledge base.

        Args:
            persist_dir: Directory for ChromaDB persistence.
            collection_name: Name of the ChromaDB collection.
        """
        self._persist_dir = Path(persist_dir)
        self._collection_name = collection_name
        self._client: Any = None
        self._collection: Any = None

    def _ensure_client(self) -> None:
        """Lazy-initialise the ChromaDB client and collection."""
        if self._client is not None:
            return

        try:
            import chromadb

            self._persist_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self._persist_dir))

            from rpa_architect.codegen.rag.embeddings import get_embedding_function

            ef = get_embedding_function()
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                embedding_function=ef,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(
                "ChromaDB collection '%s' ready (%d documents).",
                self._collection_name,
                self._collection.count(),
            )
        except ImportError:
            logger.warning(
                "ChromaDB is not installed — RAG knowledge base is disabled. "
                "Install with: pip install chromadb"
            )
            self._client = None
            self._collection = None

    def build_index(self, knowledge_dir: Path) -> int:
        """Index all eligible files from a directory tree.

        Args:
            knowledge_dir: Root directory to scan for .md, .cs, .json files.

        Returns:
            Number of chunks indexed.
        """
        self._ensure_client()
        if self._collection is None:
            logger.warning("No ChromaDB collection — skipping index build.")
            return 0

        from rpa_architect.codegen.rag.embeddings import chunk_document

        knowledge_dir = Path(knowledge_dir)
        if not knowledge_dir.is_dir():
            logger.warning("Knowledge directory does not exist: %s", knowledge_dir)
            return 0

        total_chunks = 0
        batch_ids: list[str] = []
        batch_docs: list[str] = []
        batch_meta: list[dict[str, Any]] = []

        for file_path in sorted(knowledge_dir.rglob("*")):
            if file_path.suffix.lower() not in self.INDEXABLE_EXTENSIONS:
                continue
            if not file_path.is_file():
                continue

            try:
                text = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                logger.warning("Cannot read %s: %s", file_path, exc)
                continue

            chunks = chunk_document(text)
            for idx, chunk in enumerate(chunks):
                doc_id = f"{file_path.stem}_{file_path.suffix.lstrip('.')}_{idx}"
                metadata = {
                    "source": str(file_path.relative_to(knowledge_dir)),
                    "file_type": file_path.suffix.lstrip("."),
                    "chunk_index": idx,
                    "total_chunks": len(chunks),
                }

                batch_ids.append(doc_id)
                batch_docs.append(chunk)
                batch_meta.append(metadata)
                total_chunks += 1

                # Upsert in batches of 100
                if len(batch_ids) >= 100:
                    self._collection.upsert(
                        ids=batch_ids,
                        documents=batch_docs,
                        metadatas=batch_meta,
                    )
                    batch_ids, batch_docs, batch_meta = [], [], []

        # Flush remaining
        if batch_ids:
            self._collection.upsert(
                ids=batch_ids,
                documents=batch_docs,
                metadatas=batch_meta,
            )

        logger.info("Indexed %d chunks from %s.", total_chunks, knowledge_dir)
        return total_chunks

    def query(self, query: str, n_results: int = 5) -> list[Document]:
        """Search the knowledge base for relevant documents.

        Args:
            query: Natural language query.
            n_results: Maximum number of results to return.

        Returns:
            List of Document objects sorted by relevance.
        """
        self._ensure_client()
        if self._collection is None:
            logger.info("Knowledge base query skipped (ChromaDB unavailable): %s", query[:100])
            return []
        if self._collection.count() == 0:
            return []

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=min(n_results, self._collection.count()),
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            logger.exception("Knowledge base query failed for: %s", query)
            return []

        documents: list[Document] = []
        if results and results.get("documents"):
            docs_list = results["documents"][0]
            meta_list = results.get("metadatas", [[]])[0]
            dist_list = results.get("distances", [[]])[0]

            for i, doc_text in enumerate(docs_list):
                metadata = meta_list[i] if i < len(meta_list) else {}
                distance = dist_list[i] if i < len(dist_list) else 1.0
                documents.append(
                    Document(
                        content=doc_text,
                        source=metadata.get("source", "unknown"),
                        metadata=metadata,
                        score=1.0 - distance,  # Convert distance to similarity
                    )
                )

        return documents

    @property
    def is_available(self) -> bool:
        """Whether the knowledge base backend is operational."""
        self._ensure_client()
        return self._collection is not None

    @property
    def document_count(self) -> int:
        """Return the number of documents in the collection."""
        self._ensure_client()
        if self._collection is None:
            return 0
        return self._collection.count()
