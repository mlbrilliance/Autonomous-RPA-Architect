"""Convert harvested DOM elements to UiPath XML selector strings.

Generates production-ready UiPath selectors from real browser-harvested
element attributes, prioritizing stable attributes (id, name, data-testid)
over volatile ones (positional index, dynamic classes).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from xml.sax.saxutils import escape

if TYPE_CHECKING:
    from rpa_architect.selectors.element_matcher import MatchResult

# Patterns indicating a dynamic/auto-generated ID
_DYNAMIC_ID_PATTERNS = [
    re.compile(r"[0-9a-f]{8,}", re.IGNORECASE),  # hex hashes
    re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-", re.IGNORECASE),  # UUIDs
    re.compile(r"^:r[0-9a-z]+:$"),  # React auto-IDs
    re.compile(r"^\d{6,}$"),  # pure numeric IDs
    re.compile(r"^(ember|react|ng|vue|ext-comp)-?\d+", re.IGNORECASE),  # framework IDs
]

# CSS classes that are likely stable (not utility/generated)
_UNSTABLE_CLASS_PATTERNS = [
    re.compile(r"^[a-z]{1,2}-[a-zA-Z0-9]{6,}$"),  # CSS modules hashes (short prefix + long hash)
    re.compile(r"^_[a-zA-Z0-9]{5,}$"),  # styled-components
    re.compile(r"^css-[a-zA-Z0-9]+$"),  # emotion
]


@dataclass
class HarvestedElement:
    """A UI element discovered from a live browser page."""

    tag: str = ""
    id: str = ""
    name: str = ""
    classes: list[str] = field(default_factory=list)
    aria_label: str = ""
    aria_role: str = ""
    inner_text: str = ""
    placeholder: str = ""
    input_type: str = ""
    data_testid: str = ""
    xpath: str = ""
    css_selector: str = ""
    bounding_box: dict[str, float] = field(default_factory=dict)
    page_url: str = ""
    accessibility_name: str = ""


def _is_dynamic_id(element_id: str) -> bool:
    """Check if an element ID looks auto-generated/dynamic."""
    if not element_id:
        return True
    return any(p.search(element_id) for p in _DYNAMIC_ID_PATTERNS)


def _is_stable_class(css_class: str) -> bool:
    """Check if a CSS class looks stable (not generated)."""
    if not css_class:
        return False
    return not any(p.match(css_class) for p in _UNSTABLE_CLASS_PATTERNS)


def _escape_attr(value: str) -> str:
    """Escape a value for use in a UiPath XML selector attribute."""
    return escape(value, {"'": "&apos;", '"': "&quot;"})


def _truncate_text(text: str, max_len: int = 50) -> str:
    """Truncate text for use in selector attributes."""
    cleaned = " ".join(text.split())  # collapse whitespace
    if len(cleaned) > max_len:
        return cleaned[:max_len]
    return cleaned


def convert_to_uipath_selector(
    element: HarvestedElement,
    app_name: str = "chrome.exe",
) -> tuple[str, float]:
    """Convert a harvested element to a UiPath XML selector string.

    Returns a tuple of (selector_xml, stability_score) where stability_score
    indicates how likely the selector is to remain valid over time.

    Args:
        element: The harvested DOM element.
        app_name: Browser executable name for the selector.

    Returns:
        Tuple of (selector_xml_string, stability_score).
    """
    html_part = f"<html app='{_escape_attr(app_name)}' />"
    attrs: list[str] = []
    stability = 0.30  # baseline for positional fallback

    tag = element.tag.lower() if element.tag else "*"
    attrs.append(f"tag='{_escape_attr(tag)}'")

    # Priority 1: Stable ID
    if element.id and not _is_dynamic_id(element.id):
        attrs.append(f"id='{_escape_attr(element.id)}'")
        stability = 0.95
    # Priority 2: name attribute
    elif element.name:
        attrs.append(f"name='{_escape_attr(element.name)}'")
        stability = 0.90
    # Priority 3: data-testid
    elif element.data_testid:
        attrs.append(f"data-testid='{_escape_attr(element.data_testid)}'")
        stability = 0.90
    # Priority 4: aria-label or visible text as aaname
    elif element.aria_label:
        attrs.append(f"aaname='{_escape_attr(element.aria_label)}'")
        stability = 0.85
    elif element.accessibility_name:
        attrs.append(f"aaname='{_escape_attr(element.accessibility_name)}'")
        stability = 0.85
    # Priority 5: Stable CSS class
    elif element.classes:
        stable = [c for c in element.classes if _is_stable_class(c)]
        if stable:
            attrs.append(f"class='{_escape_attr(stable[0])}'")
            stability = 0.70
    # Priority 6: Short static innertext
    if stability < 0.60 and element.inner_text:
        text = _truncate_text(element.inner_text)
        if text and len(text) <= 50:
            attrs.append(f"innertext='{_escape_attr(text)}'")
            stability = max(stability, 0.60)

    # Add input type for disambiguation when available
    if element.input_type and element.tag.lower() == "input":
        attrs.append(f"type='{_escape_attr(element.input_type)}'")

    webctrl_attrs = " ".join(attrs)
    selector_xml = f"{html_part}<webctrl {webctrl_attrs} />"

    return selector_xml, stability


def batch_convert(
    matches: list[MatchResult],
    app_name: str = "chrome.exe",
) -> dict[str, str]:
    """Convert a list of match results to UiPath selectors.

    Args:
        matches: List of MatchResult objects from element_matcher.
        app_name: Browser executable name.

    Returns:
        Dictionary mapping element_name -> selector_xml.
    """
    result: dict[str, str] = {}
    for match in matches:
        if match.element is not None:
            selector_xml, _ = convert_to_uipath_selector(match.element, app_name)
            result[match.element_name] = selector_xml
    return result
