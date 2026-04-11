"""UiPath selector XML validation."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SelectorIssue(BaseModel):
    """A single issue found in a selector."""

    severity: str = "error"
    """One of: error, warning, info."""
    message: str
    """Human-readable description."""
    node_tag: str = ""
    """The XML tag where the issue was found."""
    attribute: str = ""
    """Attribute name involved, if any."""


class SelectorValidationResult(BaseModel):
    """Aggregated validation result for a single selector string."""

    valid: bool = True
    selector_xml: str = ""
    issues: list[SelectorIssue] = Field(default_factory=list)


# Valid UiPath selector node tags
_VALID_TAGS = {"wnd", "html", "ctrl", "java", "sap", "aa", "uia", "webctrl", "nav"}

# Common valid attributes per node type
_VALID_ATTRIBUTES: dict[str, set[str]] = {
    "wnd": {"app", "cls", "title", "aaname", "idx", "isleaf", "role", "automationid"},
    "html": {"tag", "id", "name", "class", "css-selector", "innertext", "title", "aaname", "idx", "parentid", "href"},
    "ctrl": {"name", "role", "type", "idx", "automationid", "aaname", "cls"},
    "java": {"name", "role", "cls", "idx", "aaname"},
    "webctrl": {"tag", "id", "name", "class", "css-selector", "aaname", "idx", "parentid", "innertext", "title"},
    "sap": {"name", "id", "type", "idx", "aaname", "cls"},
    "aa": {"name", "role", "type", "idx"},
    "uia": {"name", "role", "type", "idx", "automationid", "cls", "aaname"},
    "nav": {"url"},
}

# Patterns that indicate placeholder / incomplete selectors
_PLACEHOLDER_PATTERNS = [
    re.compile(r"\{\{.*?\}\}"),          # {{ placeholder }}
    re.compile(r"\<TODO\>", re.I),       # <TODO>
    re.compile(r"PLACEHOLDER", re.I),
    re.compile(r"CHANGE_ME", re.I),
    re.compile(r"XXX"),
    re.compile(r"\*\*\*"),
]


def _check_placeholder_values(selector_xml: str) -> list[SelectorIssue]:
    """Detect placeholder or incomplete values in the selector string."""
    issues: list[SelectorIssue] = []
    for pattern in _PLACEHOLDER_PATTERNS:
        if pattern.search(selector_xml):
            issues.append(
                SelectorIssue(
                    severity="warning",
                    message=f"Selector contains placeholder pattern: {pattern.pattern}",
                )
            )
    return issues


def _validate_node(element: ET.Element) -> list[SelectorIssue]:
    """Validate a single selector XML node."""
    issues: list[SelectorIssue] = []
    tag = element.tag.lower()

    # Check tag validity
    if tag not in _VALID_TAGS:
        issues.append(
            SelectorIssue(
                severity="error",
                message=f"Unknown selector node tag: <{element.tag}/>. "
                        f"Valid tags: {', '.join(sorted(_VALID_TAGS))}.",
                node_tag=element.tag,
            )
        )
        return issues  # Can't validate attributes of unknown node

    # Check attributes
    valid_attrs = _VALID_ATTRIBUTES.get(tag, set())
    for attr_name, attr_value in element.attrib.items():
        attr_lower = attr_name.lower()

        if attr_lower not in valid_attrs:
            issues.append(
                SelectorIssue(
                    severity="warning",
                    message=f"Uncommon attribute '{attr_name}' on <{tag}/>. "
                            f"Expected attributes: {', '.join(sorted(valid_attrs))}.",
                    node_tag=tag,
                    attribute=attr_name,
                )
            )

        # Check for empty attribute values
        if not attr_value.strip():
            issues.append(
                SelectorIssue(
                    severity="error",
                    message=f"Empty value for attribute '{attr_name}' on <{tag}/>.",
                    node_tag=tag,
                    attribute=attr_name,
                )
            )

        # Check for wildcard-only values (too broad)
        if attr_value.strip() == "*":
            issues.append(
                SelectorIssue(
                    severity="warning",
                    message=f"Wildcard-only value for '{attr_name}' on <{tag}/> — "
                            "selector may match unintended elements.",
                    node_tag=tag,
                    attribute=attr_name,
                )
            )

    # Validate child nodes recursively
    for child in element:
        issues.extend(_validate_node(child))

    return issues


def validate_selector(selector_xml: str) -> SelectorValidationResult:
    """Validate a UiPath selector XML string.

    Args:
        selector_xml: The selector string, e.g.
            ``<wnd app='notepad.exe' cls='Notepad' />``.

    Returns:
        Validation result with any issues found.
    """
    result = SelectorValidationResult(selector_xml=selector_xml)

    if not selector_xml or not selector_xml.strip():
        result.valid = False
        result.issues.append(
            SelectorIssue(severity="error", message="Selector is empty.")
        )
        return result

    # Check for placeholders
    result.issues.extend(_check_placeholder_values(selector_xml))

    # Parse XML
    xml_str = selector_xml.strip()
    # UiPath selectors may not have a single root — wrap if needed
    if not xml_str.startswith("<"):
        result.valid = False
        result.issues.append(
            SelectorIssue(
                severity="error",
                message="Selector does not start with '<' — invalid XML.",
            )
        )
        return result

    # Wrap in a root element for parsing if there are multiple top-level nodes
    wrapped = f"<_root_>{xml_str}</_root_>"
    try:
        root = ET.fromstring(wrapped)
    except ET.ParseError as exc:
        result.valid = False
        result.issues.append(
            SelectorIssue(
                severity="error",
                message=f"Selector is not valid XML: {exc}",
            )
        )
        return result

    # Validate each top-level node
    if len(root) == 0:
        result.valid = False
        result.issues.append(
            SelectorIssue(
                severity="error",
                message="Selector contains no recognisable nodes.",
            )
        )
        return result

    for child in root:
        result.issues.extend(_validate_node(child))

    # Overall validity: no errors
    result.valid = not any(i.severity == "error" for i in result.issues)
    return result
