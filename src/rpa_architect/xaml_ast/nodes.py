"""Typed AST nodes for UiPath XAML.

These are lightweight dataclasses, not Pydantic models. Pydantic's validation
and serialization overhead is wasted here — the nodes wrap an `lxml` element
and exist only to give callers a typed surface for read/mutate/write cycles.

The underlying lxml element is kept on each node so the writer can serialize
back to XML *with attribute order and namespace declarations preserved*.
Standard library ``xml.etree.ElementTree`` reorders attributes and reshuffles
namespace declarations on write — unacceptable for round-tripping XAML that
UiPath Studio will diff.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


@dataclass
class XamlNode:
    """Base for every AST node. Holds the xpath back-reference + lxml handle."""

    xpath: str
    # lxml element — excluded from equality/repr to keep test output sane
    element: Any = field(default=None, repr=False, compare=False)


@dataclass
class XamlSelector(XamlNode):
    """A ``<ui:Target>`` with its Selector + optional WindowSelector strings.

    The selector strings are already XML-unescaped by the parser.
    """

    selector_xml: str = ""
    window_selector: str = ""
    wait_for_ready: str = ""
    timeout_ms: str = ""


@dataclass
class XamlActivity(XamlNode):
    """Any XAML activity element (Click, Sequence, TypeInto, LogMessage, …).

    ``activity_type`` is the local tag name without namespace prefix.
    ``properties`` holds all raw string attributes (DisplayName, Level, Text, …).
    ``children`` holds nested activities and targets (but NOT property-element
    nodes like ``<ui:Click.Target>`` — those are flattened into the child list
    as ``XamlSelector`` instances).
    """

    activity_type: str = ""
    properties: dict[str, str] = field(default_factory=dict)
    children: list[XamlNode] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        """Convenience accessor for the DisplayName attribute."""
        return self.properties.get("DisplayName", "")


@dataclass
class XamlDocument:
    """A parsed XAML document.

    Holds the root activity plus the namespace map (prefix → URI) extracted
    from the document element. The original lxml ``ElementTree`` is retained
    so the writer can serialize without rebuilding the namespace context.
    """

    root: XamlActivity
    namespaces: dict[str, str] = field(default_factory=dict)
    tree: Any = field(default=None, repr=False, compare=False)
