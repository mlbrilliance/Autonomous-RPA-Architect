"""Parse XAML into a typed AST.

Uses ``lxml.etree`` because it preserves attribute order and namespace
declarations on round-trip, and because it can produce canonical xpath
strings via ``getroottree().getpath(elem)``.

The reader is tolerant of Jinja-rendered XAML (unescaped ``{{ expr }}``
tokens are already resolved before parse time) and of the XAML property
element syntax ``<ui:Click.Target>…</ui:Click.Target>``, which is
flattened so that any ``<ui:Target>`` under a property element surfaces
as a ``XamlSelector`` child of the parent activity.
"""

from __future__ import annotations

from typing import Any

from lxml import etree

from rpa_architect.xaml_ast.nodes import (
    XamlActivity,
    XamlDocument,
    XamlNode,
    XamlSelector,
)


class XamlParseError(Exception):
    """Raised when XAML content cannot be parsed as XML."""


def read_xaml(xml_content: str) -> XamlDocument:
    """Parse ``xml_content`` and return a :class:`XamlDocument`.

    Raises :class:`XamlParseError` for empty input or XML syntax errors.
    """
    if not xml_content or not xml_content.strip():
        raise XamlParseError("XAML content is empty")

    parser = etree.XMLParser(
        remove_blank_text=False,
        resolve_entities=False,
        no_network=True,
        huge_tree=False,
    )
    try:
        tree = etree.fromstring(xml_content.encode("utf-8"), parser=parser).getroottree()
    except etree.XMLSyntaxError as exc:  # pragma: no cover - passthrough
        raise XamlParseError(f"XML parse error: {exc}") from exc

    root_elem = tree.getroot()
    namespaces = _collect_namespaces(root_elem)
    root_node = _build_activity(root_elem, tree)

    return XamlDocument(root=root_node, namespaces=namespaces, tree=tree)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _collect_namespaces(root: Any) -> dict[str, str]:
    """Flatten nsmap from root. lxml uses ``None`` for the default namespace;
    we translate that to the empty string to match xaml_lint's convention."""
    nsmap: dict[str, str] = {}
    for prefix, uri in root.nsmap.items():
        nsmap["" if prefix is None else prefix] = uri
    return nsmap


def _local_name(tag: str) -> str:
    """Strip Clark-notation namespace from an lxml tag: ``{uri}Click`` → ``Click``."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _is_property_element(tag: str) -> bool:
    """``ui:Click.Target``-style property elements contain a dot in the local name."""
    return "." in _local_name(tag)


def _build_activity(elem: Any, tree: Any) -> XamlActivity:
    """Recursively build a XamlActivity from an lxml element."""
    xpath = tree.getpath(elem)
    properties = {_local_name(k): v for k, v in elem.attrib.items()}

    node = XamlActivity(
        xpath=xpath,
        element=elem,
        activity_type=_local_name(elem.tag),
        properties=properties,
        children=[],
    )

    for child in elem:
        # Skip comments and processing instructions
        if not isinstance(child.tag, str):
            continue
        node.children.extend(_build_child(child, tree))

    return node


def _build_child(elem: Any, tree: Any) -> list[XamlNode]:
    """Dispatch: property-element → flatten; ``ui:Target`` → selector; else activity.

    Property elements like ``<ui:Click.Target>…</ui:Click.Target>`` are
    *syntactic sugar* in XAML; they hold child elements that logically belong
    to the parent activity. We descend into them and lift their children up.
    """
    tag = elem.tag
    if not isinstance(tag, str):
        return []

    local = _local_name(tag)

    if local == "Target":
        return [_build_selector(elem, tree)]

    if _is_property_element(tag):
        # e.g. <ui:Click.Target> — descend and yield whatever children it holds.
        out: list[XamlNode] = []
        for grand in elem:
            if not isinstance(grand.tag, str):
                continue
            out.extend(_build_child(grand, tree))
        return out

    return [_build_activity(elem, tree)]


def _build_selector(elem: Any, tree: Any) -> XamlSelector:
    """Build a XamlSelector node from a ``<ui:Target>`` element."""
    xpath = tree.getpath(elem)
    props = {_local_name(k): v for k, v in elem.attrib.items()}
    return XamlSelector(
        xpath=xpath,
        element=elem,
        selector_xml=props.get("Selector", ""),
        window_selector=props.get("WindowSelector", ""),
        wait_for_ready=props.get("WaitForReady", ""),
        timeout_ms=props.get("Timeout", ""),
    )
