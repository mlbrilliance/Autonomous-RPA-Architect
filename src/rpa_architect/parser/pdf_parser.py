"""PDF parser implementation using pdfplumber.

Extracts text sections, tables, and images from PDF-format Process Design Documents.
Handles multi-column layouts and detects section headings by font size.
"""

from __future__ import annotations

import io
import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from rpa_architect.parser.base import PddContent, PddSection, PddTable

logger = logging.getLogger(__name__)


class _HeadingCandidate(BaseModel):
    """Internal model for heading detection."""

    text: str
    font_size: float
    page_number: int
    y_position: float


class PdfParser:
    """Parse PDF-format PDD documents using pdfplumber.

    Extracts text with section detection based on font sizes, tables with
    headers, and embedded images. Handles multi-column layouts by sorting
    text elements by position.
    """

    # Font-size thresholds for heading levels (points)
    HEADING_THRESHOLDS: list[tuple[float, int]] = [
        (18.0, 1),  # >= 18pt -> H1
        (15.0, 2),  # >= 15pt -> H2
        (13.0, 3),  # >= 13pt -> H3
        (11.5, 4),  # >= 11.5pt -> H4
    ]

    # Minimum text length to consider as meaningful content
    MIN_CONTENT_LENGTH = 5

    def parse(self, path: Path) -> PddContent:
        """Parse a PDF file and extract structured content.

        Args:
            path: Path to the PDF file.

        Returns:
            PddContent with sections, tables, images, and metadata.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file is not a valid PDF.
        """
        try:
            import pdfplumber
        except ImportError as exc:
            raise ImportError(
                "pdfplumber is required for PDF parsing. "
                "Install it with: pip install pdfplumber"
            ) from exc

        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {path}")

        if not path.suffix.lower() == ".pdf":
            raise ValueError(f"Expected a .pdf file, got: {path.suffix}")

        sections: list[PddSection] = []
        tables: list[PddTable] = []
        images: list[bytes] = []
        metadata: dict[str, Any] = {}

        with pdfplumber.open(path) as pdf:
            # Extract PDF metadata
            if pdf.metadata:
                for key, value in pdf.metadata.items():
                    if value:
                        metadata[key] = str(value)

            metadata["page_count"] = len(pdf.pages)

            for page_num, page in enumerate(pdf.pages, start=1):
                # Extract tables from this page
                page_tables = self._extract_tables(page, page_num)
                tables.extend(page_tables)

                # Extract text sections with heading detection
                page_sections = self._extract_sections(page, page_num)
                sections.extend(page_sections)

                # Extract images
                page_images = self._extract_images(page)
                images.extend(page_images)

        # Merge consecutive sections at the same level into coherent blocks
        sections = self._merge_sections(sections)

        return PddContent(
            sections=sections,
            tables=tables,
            images=images,
            metadata=metadata,
        )

    def _extract_sections(self, page: Any, page_number: int) -> list[PddSection]:
        """Extract text sections from a page using font-size-based heading detection.

        Handles multi-column layouts by sorting characters by their x then y position
        to reconstruct reading order.
        """
        chars = page.chars
        if not chars:
            # Fallback: just get the full text
            text = page.extract_text() or ""
            if text.strip():
                return [
                    PddSection(
                        title="",
                        content=text.strip(),
                        level=1,
                        page_number=page_number,
                    )
                ]
            return []

        # Sort characters by reading order: top-to-bottom, left-to-right
        # For multi-column detection, split page into columns if text clusters
        page_width = page.width
        mid_x = page_width / 2

        # Detect if page is multi-column by checking character distribution
        left_chars = [c for c in chars if float(c.get("x0", 0)) < mid_x * 0.9]
        right_chars = [c for c in chars if float(c.get("x0", 0)) > mid_x * 1.1]

        is_multi_column = (
            len(left_chars) > 20
            and len(right_chars) > 20
            and len(right_chars) > len(chars) * 0.2
        )

        if is_multi_column:
            # Process left column then right column
            ordered_chars = sorted(
                left_chars, key=lambda c: (float(c.get("top", 0)), float(c.get("x0", 0)))
            ) + sorted(
                right_chars, key=lambda c: (float(c.get("top", 0)), float(c.get("x0", 0)))
            )
        else:
            ordered_chars = sorted(
                chars, key=lambda c: (float(c.get("top", 0)), float(c.get("x0", 0)))
            )

        # Group characters into lines
        lines = self._group_chars_into_lines(ordered_chars)

        # Detect headings and build sections
        sections: list[PddSection] = []
        current_heading: str = ""
        current_level: int = 1
        current_content_lines: list[str] = []

        for line_text, avg_font_size, is_bold in lines:
            heading_level = self._detect_heading_level(line_text, avg_font_size, is_bold)

            if heading_level is not None:
                # Save previous section if it has content
                if current_heading or current_content_lines:
                    sections.append(
                        PddSection(
                            title=current_heading,
                            content="\n".join(current_content_lines).strip(),
                            level=current_level,
                            page_number=page_number,
                        )
                    )

                current_heading = line_text.strip()
                current_level = heading_level
                current_content_lines = []
            else:
                if line_text.strip():
                    current_content_lines.append(line_text.strip())

        # Don't forget the last section
        if current_heading or current_content_lines:
            sections.append(
                PddSection(
                    title=current_heading,
                    content="\n".join(current_content_lines).strip(),
                    level=current_level,
                    page_number=page_number,
                )
            )

        return sections

    def _group_chars_into_lines(
        self, chars: list[dict[str, Any]]
    ) -> list[tuple[str, float, bool]]:
        """Group characters into lines based on vertical position.

        Returns:
            List of (line_text, average_font_size, is_bold) tuples.
        """
        if not chars:
            return []

        lines: list[tuple[str, float, bool]] = []
        current_line_chars: list[dict[str, Any]] = [chars[0]]
        line_tolerance = 3.0  # points

        for char in chars[1:]:
            prev_top = float(current_line_chars[-1].get("top", 0))
            curr_top = float(char.get("top", 0))

            if abs(curr_top - prev_top) <= line_tolerance:
                current_line_chars.append(char)
            else:
                # Finalize current line
                line_data = self._finalize_line(current_line_chars)
                if line_data:
                    lines.append(line_data)
                current_line_chars = [char]

        # Finalize last line
        if current_line_chars:
            line_data = self._finalize_line(current_line_chars)
            if line_data:
                lines.append(line_data)

        return lines

    def _finalize_line(
        self, chars: list[dict[str, Any]]
    ) -> tuple[str, float, bool] | None:
        """Convert a group of characters into a line with metadata."""
        if not chars:
            return None

        # Sort by x position within the line
        sorted_chars = sorted(chars, key=lambda c: float(c.get("x0", 0)))

        text_parts: list[str] = []
        sizes: list[float] = []
        bold_count = 0

        prev_x1 = None
        for char in sorted_chars:
            char_text = char.get("text", "")
            if not char_text:
                continue

            x0 = float(char.get("x0", 0))
            size = float(char.get("size", 12))
            fontname = str(char.get("fontname", "")).lower()

            # Detect spaces between characters
            if prev_x1 is not None and (x0 - prev_x1) > size * 0.3:
                text_parts.append(" ")

            text_parts.append(char_text)
            sizes.append(size)

            if "bold" in fontname or "heavy" in fontname:
                bold_count += 1

            prev_x1 = float(char.get("x1", x0 + size))

        text = "".join(text_parts).strip()
        if not text or len(text) < 1:
            return None

        avg_size = sum(sizes) / len(sizes) if sizes else 12.0
        is_bold = bold_count > len(chars) * 0.5

        return (text, avg_size, is_bold)

    def _detect_heading_level(
        self, text: str, font_size: float, is_bold: bool
    ) -> int | None:
        """Detect if a line is a heading based on font size and formatting.

        Returns heading level (1-4) or None if it's body text.
        """
        text = text.strip()

        # Skip very long lines (unlikely to be headings)
        if len(text) > 150:
            return None

        # Skip lines that look like sentences (end with period, contain many words)
        if text.endswith(".") and len(text.split()) > 10:
            return None

        # Check numbered heading patterns (e.g., "1.", "1.1", "1.1.1")
        numbered_match = re.match(r"^(\d+(?:\.\d+)*)\s+\S", text)
        if numbered_match:
            depth = numbered_match.group(1).count(".") + 1
            return min(depth, 4)

        # Check font size thresholds
        for threshold, level in self.HEADING_THRESHOLDS:
            if font_size >= threshold:
                return level

        # Bold short text is likely a heading
        if is_bold and len(text.split()) <= 8 and len(text) > 2:
            return 4

        return None

    def _extract_tables(self, page: Any, page_number: int) -> list[PddTable]:
        """Extract tables from a page."""
        extracted_tables: list[PddTable] = []

        try:
            raw_tables = page.extract_tables()
        except Exception:
            logger.debug("Failed to extract tables from page %d", page_number)
            return []

        if not raw_tables:
            return []

        for table_data in raw_tables:
            if not table_data or len(table_data) < 1:
                continue

            # Clean cell values
            cleaned = []
            for row in table_data:
                cleaned_row = [
                    (cell.strip() if isinstance(cell, str) else str(cell or "").strip())
                    for cell in (row or [])
                ]
                cleaned.append(cleaned_row)

            # First row as headers if it looks like a header row
            if len(cleaned) >= 2:
                headers = cleaned[0]
                rows = cleaned[1:]
            elif len(cleaned) == 1:
                headers = cleaned[0]
                rows = []
            else:
                continue

            # Skip empty tables
            if all(not h for h in headers) and not rows:
                continue

            extracted_tables.append(
                PddTable(
                    headers=headers,
                    rows=rows,
                    caption="",
                    page_number=page_number,
                )
            )

        return extracted_tables

    def _extract_images(self, page: Any) -> list[bytes]:
        """Extract embedded images from a page."""
        extracted_images: list[bytes] = []

        try:
            if not hasattr(page, "images") or not page.images:
                return []

            for img_info in page.images:
                try:
                    # pdfplumber provides image metadata; we need to extract the actual bytes
                    # from the page's underlying PDF object
                    if hasattr(page, "page") and hasattr(page.page, "images"):
                        # Try to get image stream from the PDF page
                        pass

                    # Alternative: crop the image region and convert to bytes
                    x0 = float(img_info.get("x0", 0))
                    y0 = float(img_info.get("top", 0))
                    x1 = float(img_info.get("x1", 0))
                    y1 = float(img_info.get("bottom", 0))

                    if x1 > x0 and y1 > y0:
                        cropped = page.crop((x0, y0, x1, y1))
                        img = cropped.to_image(resolution=150)
                        buf = io.BytesIO()
                        img.save(buf, format="PNG")
                        extracted_images.append(buf.getvalue())
                except Exception:
                    logger.debug("Failed to extract an image from page")
                    continue

        except Exception:
            logger.debug("Failed to process images on page")

        return extracted_images

    def _merge_sections(self, sections: list[PddSection]) -> list[PddSection]:
        """Merge consecutive untitled sections into the previous titled section."""
        if not sections:
            return []

        merged: list[PddSection] = []
        for section in sections:
            if (
                not section.title
                and merged
                and merged[-1].page_number == section.page_number
            ):
                # Append content to the previous section
                prev = merged[-1]
                merged[-1] = PddSection(
                    title=prev.title,
                    content=(prev.content + "\n" + section.content).strip(),
                    level=prev.level,
                    page_number=prev.page_number,
                )
            else:
                merged.append(section)

        return merged
