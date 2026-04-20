"""Walk a ``XamlDocument``, surface every selector, and support in-place patching.

This is the shared interface both features depend on:

* **Self-Healing Swarm** — the selector-repair specialist extracts every
  selector from the deployed XAML, picks the one that matches the broken
  activity in the failure bundle, and calls :func:`patch_selector` with a
  fresh selector string harvested from the live UI.

* **XAML → Python+Playwright Migrator** — the IR lifter walks the AST,
  delegates to the selector translator for each ``ExtractedSelector``, and
  emits a Playwright locator chain in the generated code.
"""

from __future__ import annotations

from dataclasses import dataclass

from rpa_architect.xaml_ast.nodes import (
    XamlActivity,
    XamlDocument,
    XamlNode,
    XamlSelector,
)


@dataclass(frozen=True)
class ExtractedSelector:
    """A selector paired with the activity that owns it.

    ``activity_xpath`` is the xpath to the **selector element itself**,
    recorded so callers can log a stable identifier. ``element`` is the
    direct lxml reference — patching should prefer this path since xpath
    evaluation with XAML's mixed default / prefixed namespaces is fragile.
    """

    activity_type: str
    activity_display_name: str
    activity_xpath: str
    selector_xml: str
    window_selector: str
    element: object = None  # lxml._Element; typed as object to avoid import churn


def extract_selectors(doc: XamlDocument) -> list[ExtractedSelector]:
    """Return every selector in the document, paired with its owning activity."""
    out: list[ExtractedSelector] = []
    _walk(doc.root, parent=None, accum=out)
    return out


def patch_selector(doc: XamlDocument, xpath: str, new_selector_xml: str) -> None:
    """Rewrite the ``Selector`` attribute of the ``<ui:Target>`` at ``xpath``.

    ``xpath`` must be the ``ExtractedSelector.activity_xpath`` value returned
    by :func:`extract_selectors`. Resolution walks the document once to find
    the element — we avoid ``tree.xpath()`` because XAML mixes a default
    namespace with prefixed namespaces and the xpath evaluator's prefix map
    is fragile across those boundaries.
    """
    if doc.tree is None:
        raise ValueError("XamlDocument has no backing lxml tree; cannot patch")

    target_elem = _find_by_xpath(doc, xpath)
    if target_elem is None:
        raise KeyError(f"No element found at xpath: {xpath}")

    for key in list(target_elem.attrib.keys()):
        if key.endswith("Selector") and not key.endswith("WindowSelector"):
            target_elem.attrib[key] = new_selector_xml
            return
    target_elem.attrib["Selector"] = new_selector_xml


def _find_by_xpath(doc: XamlDocument, xpath: str) -> object | None:
    """Walk the tree and return the first element whose ``getpath()`` matches."""
    tree = doc.tree
    root = tree.getroot()
    for elem in root.iter():
        if tree.getpath(elem) == xpath:
            return elem
    return None


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _walk(
    node: XamlNode,
    parent: XamlActivity | None,
    accum: list[ExtractedSelector],
) -> None:
    if isinstance(node, XamlSelector):
        assert parent is not None, "Selector without an owning activity"
        accum.append(
            ExtractedSelector(
                activity_type=parent.activity_type,
                activity_display_name=parent.display_name,
                activity_xpath=node.xpath,
                selector_xml=node.selector_xml,
                window_selector=node.window_selector,
                element=node.element,
            )
        )
        return

    if isinstance(node, XamlActivity):
        for child in node.children:
            _walk(child, parent=node, accum=accum)
