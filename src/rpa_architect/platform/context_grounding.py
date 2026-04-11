"""UiPath Context Grounding RAG integration."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger("rpa_architect.platform.context_grounding")

_DEFAULT_TIMEOUT = 60.0


class Document(BaseModel):
    """A document chunk returned from Context Grounding."""

    content: str = ""
    source: str = ""
    score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class UiPathContextGrounding:
    """Client for the UiPath Context Grounding RAG service.

    Handles service unavailability gracefully by returning empty results
    rather than raising.

    Args:
        base_url: Context Grounding service URL.
        api_key: Authentication key.
    """

    def __init__(
        self,
        base_url: str = "https://context-grounding.uipath.com",
        api_key: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def query(
        self,
        text: str,
        index_name: str,
        n_results: int = 5,
    ) -> list[Document]:
        """Query the Context Grounding index for relevant documents.

        Args:
            text: Query text.
            index_name: Name of the grounding index to search.
            n_results: Maximum number of results to return.

        Returns:
            A list of :class:`Document` instances, possibly empty if the
            service is unavailable.
        """
        url = f"{self._base_url}/api/v1/indexes/{index_name}/query"
        payload = {"query": text, "top_k": n_results}

        try:
            async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
                response = await client.post(
                    url, json=payload, headers=self._headers()
                )
                response.raise_for_status()
                data = response.json()

            documents: list[Document] = []
            for item in data.get("results", []):
                documents.append(
                    Document(
                        content=item.get("content", ""),
                        source=item.get("source", ""),
                        score=float(item.get("score", 0.0)),
                        metadata=item.get("metadata", {}),
                    )
                )

            logger.info(
                "Context Grounding returned %d results for index '%s'",
                len(documents),
                index_name,
            )
            return documents

        except httpx.HTTPError as exc:
            logger.warning(
                "Context Grounding query failed for index '%s': %s",
                index_name,
                exc,
            )
            return []
        except Exception as exc:
            logger.warning(
                "Unexpected error querying Context Grounding: %s", exc
            )
            return []
