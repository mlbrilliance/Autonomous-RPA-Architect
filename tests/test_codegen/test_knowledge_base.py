"""Tests for RAG knowledge base graceful degradation."""

from __future__ import annotations

import logging
from unittest.mock import patch

from rpa_architect.codegen.rag.knowledge_base import KnowledgeBase


class TestKnowledgeBaseWithoutChromaDB:
    """Verify behavior when ChromaDB is not installed."""

    def _make_kb_without_chromadb(self) -> KnowledgeBase:
        """Create a KnowledgeBase that simulates missing ChromaDB."""
        kb = KnowledgeBase()
        # Simulate failed import by setting internals directly
        kb._client = None
        kb._collection = None
        return kb

    def test_query_returns_empty(self):
        kb = self._make_kb_without_chromadb()
        # Bypass _ensure_client to test the None path
        with patch.object(kb, "_ensure_client"):
            results = kb.query("test query")
        assert results == []

    def test_is_available_false(self):
        kb = self._make_kb_without_chromadb()
        with patch.object(kb, "_ensure_client"):
            assert kb.is_available is False

    def test_document_count_zero(self):
        kb = self._make_kb_without_chromadb()
        with patch.object(kb, "_ensure_client"):
            assert kb.document_count == 0

    def test_build_index_returns_zero(self, tmp_path):
        kb = self._make_kb_without_chromadb()
        with patch.object(kb, "_ensure_client"):
            count = kb.build_index(tmp_path)
        assert count == 0

    def test_query_logs_info_when_unavailable(self, caplog):
        kb = self._make_kb_without_chromadb()
        with patch.object(kb, "_ensure_client"), \
             caplog.at_level(logging.INFO, logger="rpa_architect.codegen.rag.knowledge_base"):
            kb.query("find uipath activities")
        assert any("ChromaDB unavailable" in r.message for r in caplog.records)
