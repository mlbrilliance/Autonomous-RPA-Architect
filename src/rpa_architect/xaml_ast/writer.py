"""Serialize a ``XamlDocument`` back to XAML.

We rely on lxml's canonical ``tostring`` because it preserves namespace
declarations and attribute insertion order from the source document.
Any mutation performed on ``XamlSelector.element`` or ``XamlActivity.element``
lxml handles (e.g. via :func:`selector_extractor.patch_selector`) is reflected
in the output.
"""

from __future__ import annotations

from lxml import etree

from rpa_architect.xaml_ast.nodes import XamlDocument


def write_xaml(doc: XamlDocument, *, pretty: bool = True) -> str:
    """Serialize the document back to a ``str``.

    The ``<?xml ...?>`` declaration is emitted at the top so UiPath Studio
    treats the file as a valid workflow.
    """
    if doc.tree is None:
        raise ValueError("XamlDocument has no backing lxml tree; cannot serialize")

    rendered = etree.tostring(
        doc.tree,
        xml_declaration=True,
        encoding="utf-8",
        pretty_print=pretty,
        standalone=False,
    )
    return rendered.decode("utf-8")
