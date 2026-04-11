"""Parser protocol and shared data models for PDD parsing."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class PddSection(BaseModel):
    """A text section extracted from a PDD document."""

    title: str = Field(description="Section heading or title.")
    content: str = Field(description="Full text content of the section.")
    level: int = Field(
        default=1,
        ge=1,
        le=6,
        description="Heading level (1 = top-level, 6 = deepest).",
    )
    page_number: int = Field(
        default=0,
        ge=0,
        description="Page number where the section starts (0 if unknown).",
    )


class PddTable(BaseModel):
    """A table extracted from a PDD document."""

    headers: list[str] = Field(
        default_factory=list, description="Column header labels."
    )
    rows: list[list[str]] = Field(
        default_factory=list, description="Table data rows."
    )
    caption: str = Field(default="", description="Table caption or title if available.")
    page_number: int = Field(
        default=0,
        ge=0,
        description="Page number where the table appears (0 if unknown).",
    )


class PddContent(BaseModel):
    """Complete parsed content from a Process Design Document."""

    sections: list[PddSection] = Field(
        default_factory=list, description="Text sections in reading order."
    )
    tables: list[PddTable] = Field(
        default_factory=list, description="Tables extracted from the document."
    )
    images: list[bytes] = Field(
        default_factory=list, description="Raw image bytes for embedded images."
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Document metadata (title, author, creation date, etc.).",
    )


@runtime_checkable
class PddParser(Protocol):
    """Protocol for PDD document parsers.

    Implementations must provide a ``parse`` method that reads a document
    from disk and returns structured PddContent.
    """

    def parse(self, path: Path) -> PddContent:
        """Parse a PDD document file and extract structured content.

        Args:
            path: Path to the document file.

        Returns:
            Parsed PddContent with sections, tables, images, and metadata.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file format is unsupported or corrupt.
        """
        ...
