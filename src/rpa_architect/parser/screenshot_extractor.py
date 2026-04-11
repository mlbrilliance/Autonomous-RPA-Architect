"""Screenshot extraction from parsed PDD content.

Extracts and contextualizes screenshots/images from PDD documents,
associating them with surrounding text for better LLM understanding.
"""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, Field

from rpa_architect.parser.base import PddContent

logger = logging.getLogger(__name__)


class Screenshot(BaseModel):
    """An extracted screenshot with contextual information."""

    image_bytes: bytes = Field(description="Raw image data.")
    page_number: int = Field(
        default=0, ge=0, description="Page where the screenshot was found."
    )
    caption: str = Field(
        default="", description="Caption or label for the screenshot."
    )
    context_text: str = Field(
        default="",
        description="Surrounding text providing context for the screenshot.",
    )
    index: int = Field(
        default=0, ge=0, description="Sequential index of the screenshot."
    )
    width: Optional[int] = Field(default=None, description="Image width in pixels.")
    height: Optional[int] = Field(default=None, description="Image height in pixels.")


def _get_image_dimensions(image_bytes: bytes) -> tuple[int | None, int | None]:
    """Try to determine image dimensions from bytes.

    Supports PNG and JPEG headers without requiring PIL.
    """
    if len(image_bytes) < 24:
        return None, None

    # PNG: bytes 16-23 contain width and height as 4-byte big-endian ints
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        try:
            width = int.from_bytes(image_bytes[16:20], "big")
            height = int.from_bytes(image_bytes[20:24], "big")
            return width, height
        except Exception:
            pass

    # JPEG: need to find SOF0 marker
    if image_bytes[:2] == b"\xff\xd8":
        try:
            offset = 2
            while offset < len(image_bytes) - 9:
                if image_bytes[offset] != 0xFF:
                    break
                marker = image_bytes[offset + 1]
                # SOF0, SOF1, SOF2 markers
                if marker in (0xC0, 0xC1, 0xC2):
                    height = int.from_bytes(image_bytes[offset + 5 : offset + 7], "big")
                    width = int.from_bytes(image_bytes[offset + 7 : offset + 9], "big")
                    return width, height
                # Skip to next marker
                length = int.from_bytes(image_bytes[offset + 2 : offset + 4], "big")
                offset += 2 + length
        except Exception:
            pass

    return None, None


def _find_caption_in_sections(content: PddContent, image_index: int) -> str:
    """Try to find a caption for an image by looking at section content.

    Searches for patterns like 'Figure N', 'Screenshot N', 'Image N' in
    the text surrounding the image's position.
    """
    import re

    caption_patterns = [
        rf"(?:Figure|Fig\.?|Screenshot|Image|Screen)\s*{image_index + 1}\s*[:\-\.]?\s*(.*?)(?:\n|$)",
        rf"(?:Figure|Fig\.?|Screenshot|Image|Screen)\s*{image_index + 1}\b",
    ]

    for section in content.sections:
        for pattern in caption_patterns:
            match = re.search(pattern, section.content, re.IGNORECASE)
            if match:
                caption = match.group(0).strip()
                return caption[:200]  # Limit caption length

    return ""


def _get_context_text(content: PddContent, image_index: int) -> str:
    """Get surrounding text context for an image.

    Uses a heuristic: if there are N images and M sections, image i
    corresponds roughly to section i * M / N. We grab text from nearby
    sections to provide context.
    """
    if not content.sections:
        return ""

    num_images = len(content.images)
    num_sections = len(content.sections)

    if num_images == 0:
        return ""

    # Estimate which section this image is near
    estimated_section_idx = min(
        int(image_index * num_sections / num_images), num_sections - 1
    )

    # Gather context from the estimated section and its neighbors
    context_parts: list[str] = []
    start = max(0, estimated_section_idx - 1)
    end = min(num_sections, estimated_section_idx + 2)

    for idx in range(start, end):
        section = content.sections[idx]
        if section.title:
            context_parts.append(f"[{section.title}]")
        if section.content:
            # Truncate long content to keep context manageable
            text = section.content[:500]
            context_parts.append(text)

    return "\n".join(context_parts)


def extract_screenshots(content: PddContent) -> list[Screenshot]:
    """Extract and contextualize screenshots from parsed PDD content.

    Associates each embedded image with its caption (if found) and
    surrounding text context from the document sections.

    Args:
        content: Parsed PDD content containing images and text.

    Returns:
        List of Screenshot objects with context information.
    """
    screenshots: list[Screenshot] = []

    for i, image_bytes in enumerate(content.images):
        # Skip trivially small images (likely icons or decorations)
        if len(image_bytes) < 500:
            logger.debug("Skipping image %d: too small (%d bytes)", i, len(image_bytes))
            continue

        # Get image dimensions
        width, height = _get_image_dimensions(image_bytes)

        # Skip very small images that are likely bullets/icons
        if width is not None and height is not None:
            if width < 50 or height < 50:
                logger.debug(
                    "Skipping image %d: too small (%dx%d)", i, width, height
                )
                continue

        # Find caption
        caption = _find_caption_in_sections(content, i)

        # Get surrounding text context
        context_text = _get_context_text(content, i)

        # Determine page number if available from sections
        page_number = 0
        if content.sections:
            num_images = len(content.images)
            num_sections = len(content.sections)
            if num_images > 0:
                est_idx = min(int(i * num_sections / num_images), num_sections - 1)
                page_number = content.sections[est_idx].page_number

        screenshots.append(
            Screenshot(
                image_bytes=image_bytes,
                page_number=page_number,
                caption=caption,
                context_text=context_text,
                index=i,
                width=width,
                height=height,
            )
        )

    logger.info(
        "Extracted %d screenshots from %d embedded images",
        len(screenshots),
        len(content.images),
    )

    return screenshots
