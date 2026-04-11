"""Retrieval-Augmented Generation for UiPath code generation."""

from rpa_architect.codegen.rag.context_builder import build_context
from rpa_architect.codegen.rag.knowledge_base import Document, KnowledgeBase

__all__ = ["Document", "KnowledgeBase", "build_context"]
