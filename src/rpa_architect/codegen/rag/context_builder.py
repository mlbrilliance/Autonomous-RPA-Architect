"""RAG context assembly for LLM prompts."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rpa_architect.codegen.planner_agent import GenerationTask
    from rpa_architect.codegen.rag.knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)

_CONTEXT_HEADER = """\
=== RAG Context ===
The following reference material was retrieved from the knowledge base.
Use it to inform your code generation — prefer patterns and APIs shown here.
"""

_SECTION_TEMPLATE = """\

--- [{source}] (relevance: {score:.2f}) ---
{content}
"""

_CONTEXT_FOOTER = """
=== End RAG Context ===
"""

MAX_CONTEXT_CHARS = 12_000
"""Hard cap on assembled context length to fit within LLM context windows."""


def build_context(
    task: "GenerationTask",
    knowledge_base: "KnowledgeBase",
    max_results_per_query: int = 3,
) -> str:
    """Retrieve and assemble RAG context for a generation task.

    Runs each of the task's ``rag_queries`` against the knowledge base,
    deduplicates results, and formats them into a structured context block
    suitable for inclusion in an LLM prompt.

    Args:
        task: The generation task containing ``rag_queries``.
        knowledge_base: An initialised KnowledgeBase instance.
        max_results_per_query: How many documents to fetch per query.

    Returns:
        Formatted context string, or empty string if no results found.
    """
    if not task.rag_queries:
        return ""

    if knowledge_base.document_count == 0:
        logger.debug("Knowledge base is empty — skipping RAG context for %s.", task.task_id)
        return ""

    # Collect unique documents across all queries
    seen_sources: set[str] = set()
    unique_docs: list[tuple[str, str, float]] = []  # (source, content, score)

    for query in task.rag_queries:
        results = knowledge_base.query(query, n_results=max_results_per_query)
        for doc in results:
            dedup_key = f"{doc.source}:{hash(doc.content[:200])}"
            if dedup_key not in seen_sources:
                seen_sources.add(dedup_key)
                unique_docs.append((doc.source, doc.content, doc.score))

    if not unique_docs:
        logger.debug("No RAG results for task %s.", task.task_id)
        return ""

    # Sort by score descending
    unique_docs.sort(key=lambda d: d[2], reverse=True)

    # Build context string with length cap
    parts: list[str] = [_CONTEXT_HEADER]
    total_len = len(_CONTEXT_HEADER) + len(_CONTEXT_FOOTER)

    for source, content, score in unique_docs:
        section = _SECTION_TEMPLATE.format(source=source, score=score, content=content)
        if total_len + len(section) > MAX_CONTEXT_CHARS:
            # Truncate this section to fit
            remaining = MAX_CONTEXT_CHARS - total_len - 50  # leave room for footer
            if remaining > 100:
                section = section[:remaining] + "\n[...truncated...]"
                parts.append(section)
            break
        parts.append(section)
        total_len += len(section)

    parts.append(_CONTEXT_FOOTER)

    context = "".join(parts)
    logger.info(
        "Built RAG context for task %s: %d docs, %d chars.",
        task.task_id,
        len(unique_docs),
        len(context),
    )
    return context
