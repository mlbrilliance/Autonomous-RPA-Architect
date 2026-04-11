"""Vision-based selector inference using Claude Vision API.

Sends screenshots to a multimodal LLM to identify UI elements and infer
UiPath-compatible selectors with confidence scores.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from rpa_architect.ir.schema import UIAction

logger = logging.getLogger(__name__)


class Screenshot(BaseModel):
    """A screenshot image for vision-based analysis."""

    path: Path = Field(description="File path to the screenshot image.")
    step_id: str = Field(
        default="",
        description="Step ID this screenshot corresponds to.",
    )
    description: str = Field(
        default="",
        description="Human-readable description of what the screenshot shows.",
    )


class SelectorInference(BaseModel):
    """Result of vision-based selector inference for a single element."""

    element_name: str = Field(description="Identifier for the UI element.")
    inferred_selector: str = Field(description="Inferred UiPath XML selector.")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in the inferred selector (0.0-1.0).",
    )
    reasoning: str = Field(
        default="",
        description="LLM reasoning about why this selector was chosen.",
    )


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for an LLM client that supports vision messages."""

    async def create_message(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str,
        max_tokens: int,
    ) -> Any: ...


def _encode_image(path: Path) -> str:
    """Read and base64-encode an image file."""
    data = path.read_bytes()
    return base64.b64encode(data).decode("utf-8")


def _get_media_type(path: Path) -> str:
    """Determine MIME type from file extension."""
    suffix = path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }
    return media_types.get(suffix, "image/png")


def _build_vision_prompt(actions: list[UIAction]) -> str:
    """Build the prompt asking the LLM to identify UI elements."""
    action_descriptions = []
    for i, action in enumerate(actions):
        desc = f"  {i + 1}. Action: {action.action}, Target: '{action.target}'"
        if action.value:
            desc += f", Value: '{action.value}'"
        action_descriptions.append(desc)

    actions_text = "\n".join(action_descriptions)

    return f"""Analyze the screenshot(s) and identify the UI elements described below.
For each element, provide a UiPath-compatible XML selector.

UI Actions to locate:
{actions_text}

For each action target, respond with a JSON array of objects containing:
- "element_name": the target name (sanitized for use as an identifier)
- "inferred_selector": a UiPath XML selector string like:
  <html app='appname.exe' /><webctrl tag='tagname' id='elementId' class='className' aaname='visible text' />
- "confidence": a float between 0.0 and 1.0 indicating how confident you are
- "reasoning": brief explanation of how you identified the element

Use the visual cues in the screenshot to determine:
- Application type (web browser, desktop app, etc.)
- HTML tag or control type
- Identifying attributes (id, name, class, accessible name, etc.)
- Hierarchy of parent containers if relevant

Respond ONLY with a valid JSON array. No markdown formatting."""


def _parse_inferences(response_text: str) -> list[SelectorInference]:
    """Parse LLM response into SelectorInference objects."""
    import json

    # Strip markdown code fences if present
    text = response_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (code fences)
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM vision response as JSON.")
        return []

    if not isinstance(data, list):
        data = [data]

    inferences: list[SelectorInference] = []
    for item in data:
        try:
            inferences.append(
                SelectorInference(
                    element_name=str(item.get("element_name", "")),
                    inferred_selector=str(item.get("inferred_selector", "")),
                    confidence=float(item.get("confidence", 0.5)),
                    reasoning=str(item.get("reasoning", "")),
                )
            )
        except (ValueError, TypeError) as exc:
            logger.warning("Skipping malformed inference entry: %s", exc)

    return inferences


async def infer_selectors(
    screenshots: list[Screenshot],
    actions: list[UIAction],
    llm_client: Any,
    *,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 4096,
) -> dict[str, str]:
    """Use vision-capable LLM to infer selectors from screenshots.

    Sends screenshots along with action descriptions to a multimodal LLM,
    which analyzes the visual UI and returns inferred selectors.

    Args:
        screenshots: List of Screenshot objects with image paths.
        actions: List of UIAction objects to find selectors for.
        llm_client: An LLM client supporting vision/multimodal messages.
            Expected to have a ``create_message`` method (Anthropic SDK style)
            or a ``messages.create`` attribute.
        model: Model identifier to use for vision inference.
        max_tokens: Maximum tokens in the LLM response.

    Returns:
        Dictionary mapping element_name -> inferred_selector XML string.
    """
    if not screenshots or not actions:
        return {}

    # Build multimodal message content
    content: list[dict[str, Any]] = []

    for screenshot in screenshots:
        if not screenshot.path.exists():
            logger.warning("Screenshot not found: %s", screenshot.path)
            continue

        image_data = _encode_image(screenshot.path)
        media_type = _get_media_type(screenshot.path)

        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": image_data,
                },
            }
        )

        if screenshot.description:
            content.append(
                {
                    "type": "text",
                    "text": f"[Screenshot context: {screenshot.description}]",
                }
            )

    content.append(
        {
            "type": "text",
            "text": _build_vision_prompt(actions),
        }
    )

    messages = [{"role": "user", "content": content}]

    # Call the LLM -- support both direct client and nested .messages attribute
    try:
        if hasattr(llm_client, "messages") and hasattr(llm_client.messages, "create"):
            response = await llm_client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=messages,
            )
        else:
            response = await llm_client.create_message(
                model=model,
                max_tokens=max_tokens,
                messages=messages,
            )
    except Exception:
        logger.exception("Vision inference LLM call failed.")
        return {}

    # Extract text from response
    if hasattr(response, "content") and isinstance(response.content, list):
        response_text = "".join(
            block.text for block in response.content if hasattr(block, "text")
        )
    elif hasattr(response, "content") and isinstance(response.content, str):
        response_text = response.content
    else:
        response_text = str(response)

    inferences = _parse_inferences(response_text)

    # Build result dict, keeping highest-confidence inference per element
    results: dict[str, str] = {}
    confidence_map: dict[str, float] = {}

    for inf in inferences:
        existing_conf = confidence_map.get(inf.element_name, -1.0)
        if inf.confidence > existing_conf:
            results[inf.element_name] = inf.inferred_selector
            confidence_map[inf.element_name] = inf.confidence

    logger.info(
        "Vision inference produced %d selectors from %d screenshots.",
        len(results),
        len(screenshots),
    )

    return results
