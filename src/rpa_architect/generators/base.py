"""Shared helpers used by all XAML activity generators."""

from __future__ import annotations

import html
import itertools
import textwrap

# ---------------------------------------------------------------------------
# Unique ID generator
# ---------------------------------------------------------------------------

_counter = itertools.count(1)


def unique_id() -> str:
    """Return an incrementing hex ID for XAML element references."""
    return f"{next(_counter):x}"


def reset_counter(start: int = 1) -> None:
    """Reset the global counter (mainly for deterministic tests)."""
    global _counter
    _counter = itertools.count(start)


# ---------------------------------------------------------------------------
# XML attribute quoting
# ---------------------------------------------------------------------------

def quote_attr(value: str) -> str:
    """XML-safe attribute value quoting.

    Escapes ``&``, ``<``, ``>``, ``"``, and ``'`` so the value can be placed
    inside an XML attribute.
    """
    return html.escape(str(value), quote=True)


# ---------------------------------------------------------------------------
# XML element builder
# ---------------------------------------------------------------------------

def xml_element(
    tag: str,
    attribs: dict[str, str] | None = None,
    children: list[str] | None = None,
    text: str | None = None,
    self_closing: bool | None = None,
) -> str:
    """Build an XML element string with proper formatting.

    Parameters
    ----------
    tag:
        The element tag name (may include namespace prefix).
    attribs:
        Mapping of attribute name to value.  Values are escaped automatically.
    children:
        List of already-formatted XML child element strings.
    text:
        Text content of the element.
    self_closing:
        Force self-closing (``<Tag />``).  When *None*, auto-detect based on
        whether *children* and *text* are empty.
    """
    attribs = attribs or {}
    children = children or []

    attr_str = ""
    if attribs:
        parts = [f'{k}="{quote_attr(v)}"' for k, v in attribs.items() if v is not None]
        if parts:
            attr_str = " " + " ".join(parts)

    has_content = bool(children) or text is not None
    if self_closing is None:
        self_closing = not has_content

    if self_closing:
        return f"<{tag}{attr_str} />"

    inner_parts: list[str] = []
    if text is not None:
        inner_parts.append(text)
    for child in children:
        inner_parts.append(indent(child))

    if inner_parts:
        inner = "\n".join(inner_parts)
        return f"<{tag}{attr_str}>\n{inner}\n</{tag}>"
    return f"<{tag}{attr_str}></{tag}>"


# ---------------------------------------------------------------------------
# Indentation helper
# ---------------------------------------------------------------------------

def indent(xml_str: str, level: int = 1) -> str:
    """Indent all lines of an XML string by *level* &times; 2 spaces."""
    prefix = "  " * level
    lines = xml_str.split("\n")
    return "\n".join(prefix + line for line in lines)


# ---------------------------------------------------------------------------
# UiPath XAML namespace header
# ---------------------------------------------------------------------------

_XAML_NAMESPACES: dict[str, str] = {
    "xmlns": "http://schemas.microsoft.com/netfx/2009/xaml/activities",
    "xmlns:mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "xmlns:mva": "clr-namespace:Microsoft.VisualBasic.Activities;assembly=System.Activities",
    "xmlns:sap": "http://schemas.microsoft.com/netfx/2009/xaml/activities/presentation",
    "xmlns:sap2010": "http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation",
    "xmlns:scg": "clr-namespace:System.Collections.Generic;assembly=mscorlib",
    "xmlns:sco": "clr-namespace:System.Collections.ObjectModel;assembly=mscorlib",
    "xmlns:sd": "clr-namespace:System.Data;assembly=System.Data.Common",
    "xmlns:ui": "http://schemas.uipath.com/workflow/activities",
    "xmlns:x": "http://schemas.microsoft.com/winfx/2006/xaml",
}


def xaml_namespace_header() -> str:
    """Return standard UiPath XAML namespace declarations as attribute strings.

    These are formatted as one attribute per line for readability.
    """
    lines = [f'  {k}="{v}"' for k, v in _XAML_NAMESPACES.items()]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ViewState block
# ---------------------------------------------------------------------------

def viewstate_block(activities: list[tuple[str, str]]) -> str:
    """Generate a ``sap:VirtualizedContainerService.HintSize`` ViewState XML block.

    Parameters
    ----------
    activities:
        List of ``(reference_id, display_name)`` tuples.
    """
    if not activities:
        return ""

    entries: list[str] = []
    for ref_id, display_name in activities:
        entry = (
            f'<sap:WorkflowViewStateService.ViewState>'
            f'\n  <scg:Dictionary x:TypeArguments="x:String, x:Object">'
            f'\n    <x:Boolean x:Key="IsExpanded">True</x:Boolean>'
            f'\n  </scg:Dictionary>'
            f'\n</sap:WorkflowViewStateService.ViewState>'
        )
        entries.append(entry)

    return "\n".join(entries)


# ---------------------------------------------------------------------------
# Sequence wrapper
# ---------------------------------------------------------------------------

def wrap_in_sequence(activities: list[str], display_name: str = "Sequence") -> str:
    """Wrap one or more activity XAML strings in a ``<Sequence>`` element."""
    ref = unique_id()
    body = "\n".join(indent(a) for a in activities)
    return (
        f'<Sequence DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="Sequence_{ref}">\n'
        f'{body}\n'
        f'</Sequence>'
    )
