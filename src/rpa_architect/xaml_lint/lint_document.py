"""LintDocument: parsed input + traversal helpers + per-instance line map.

Replaces the old ``_line_map`` module-level dict (which two concurrent
lint runs would trash) with a per-document line index. Also exposes the
helpers (``local_name``, ``activities()``, ``is_property_accessor``)
that every XAML rule needed but each rule file used to re-implement.

Two flavours, picked by ``ContentKind``:

- ``LintDocument.from_xaml(text)`` — parses XML, builds tree + line map.
- ``LintDocument.from_coded(text, path)`` — wraps raw C# source.

A rule reads only what its ``applies_to`` permits; the engine filters.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rpa_architect.xaml_lint.rule import ContentKind

if TYPE_CHECKING:
    from pathlib import Path

# Tags that are structural parts of activities rather than activities themselves.
# Centralized here (was duplicated in rules_hallucination.py) so all XAML rules
# share one classifier.
_STRUCTURAL_TAGS: frozenset[str] = frozenset(
    {
        "Activity",
        "Members",
        "Property",
        "TextExpression",
        "WorkflowViewState",
        "ViewStateData",
        "ViewStateManager",
        "WorkflowViewStateService",
        "Literal",
        "Reference",
        "AssemblyReference",
        "Argument",
        "Variable",
        "VisualBasicSettings",
        "VisualBasicReference",
        "VisualBasicImport",
        "VisualBasicImportReference",
        "VisualBasicValue",
        "CSharpValue",
        "CSharpReference",
        "InArgument",
        "OutArgument",
        "InOutArgument",
        "Collection",
        "Dictionary",
        "List",
        "Imports",
        "NamespacesForImplementation",
        "StateMachine",
        "State",
        "StateReference",
        "Transition",
        "DelegateInArgument",
        "ActivityAction",
        "Target",
    }
)

# Sub-element tags that are property accessors (e.g. If.Then, TryCatch.Try).
_PROPERTY_ACCESSOR_RE = re.compile(r"^[A-Z]\w+\.\w+$")


def _local_name(tag: str) -> str:
    """Strip ``{namespace-uri}`` and ``prefix:`` prefixes from a tag name."""
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    if ":" in tag:
        return tag.split(":", 1)[1]
    return tag


@dataclass
class LintDocument:
    """Parsed lint input. XAML or coded; rules dispatch by ``kind``.

    For XAML docs, ``tree`` is the root :class:`xml.etree.ElementTree.Element`
    and ``_line_of_id`` maps ``id(elem) → 1-based source line``. For coded
    docs, only ``source_text`` and ``path`` are populated.
    """

    kind: ContentKind
    source_text: str
    path: "Path | None" = None
    tree: ET.Element | None = None
    namespaces: dict[str, str] = field(default_factory=dict)
    _line_of_id: dict[int, int] = field(default_factory=dict)
    parse_error: str | None = None

    # ─────────── constructors ───────────

    @classmethod
    def from_xaml(cls, content: str, path: "Path | None" = None) -> LintDocument:
        """Parse XAML content into a document.

        On parse failure, returns a document with ``parse_error`` set so
        callers can emit XL-PARSE without crashing the engine.
        """
        doc = cls(kind=ContentKind.XAML, source_text=content, path=path)

        namespaces: dict[str, str] = {}
        for match in re.finditer(r'xmlns(?::(\w+))?=["\']([^"\']+)["\']', content):
            prefix = match.group(1) or ""
            uri = match.group(2)
            namespaces[prefix] = uri
        doc.namespaces = namespaces

        try:
            parser = ET.XMLParser()
            parser.feed(content)
            doc.tree = parser.close()
        except ET.ParseError as exc:
            doc.parse_error = str(exc)
            return doc

        doc._build_line_map()
        return doc

    @classmethod
    def from_coded(cls, content: str, path: "Path | None" = None) -> LintDocument:
        """Wrap raw C# source for coded-workflow rules."""
        return cls(kind=ContentKind.CODED, source_text=content, path=path)

    # ─────────── XAML-rule helpers ───────────

    def line_of(self, element: ET.Element) -> int:
        """Return the approximate 1-based source line for *element*, or 0."""
        return self._line_of_id.get(id(element), 0)

    def local_name(self, element_or_tag: ET.Element | str) -> str:
        """Strip namespace + prefix from a tag (or an element's tag)."""
        tag = element_or_tag.tag if isinstance(element_or_tag, ET.Element) else element_or_tag
        return _local_name(tag)

    def is_structural(self, element: ET.Element) -> bool:
        """True if the element is a XAML framework tag, not a real activity."""
        return self.local_name(element) in _STRUCTURAL_TAGS

    def is_property_accessor(self, element: ET.Element) -> bool:
        """True if the element is a property accessor (e.g. ``If.Then``)."""
        return bool(_PROPERTY_ACCESSOR_RE.match(self.local_name(element)))

    def iter_all(self) -> Iterator[ET.Element]:
        """Iterate every element in the tree (delegates to ``tree.iter()``)."""
        if self.tree is None:
            return iter(())
        return self.tree.iter()

    def activities(self) -> Iterator[ET.Element]:
        """Iterate elements that are user-authored activities.

        Skips structural tags and property accessors. Use this when a
        rule cares about "real" activities; reach for :meth:`iter_all`
        when the rule needs framework tags too.
        """
        for elem in self.iter_all():
            if self.is_structural(elem) or self.is_property_accessor(elem):
                continue
            yield elem

    # ─────────── internal ───────────

    def _build_line_map(self) -> None:
        """Best-effort population of ``_line_of_id`` for every element.

        ElementTree doesn't track source positions natively; we walk the
        raw text once and assign each element the next-unmatched
        occurrence of its local tag in document order. Heuristic but
        good enough for IDE-style "click to line" UX.
        """
        if self.tree is None:
            return
        lines = self.source_text.split("\n")

        tag_line_map: dict[str, list[int]] = {}
        for line_no, line_text in enumerate(lines, start=1):
            for m in re.finditer(r"<([A-Za-z_][\w:.]*)", line_text):
                tag = m.group(1)
                local = tag.split(":")[-1] if ":" in tag else tag
                tag_line_map.setdefault(local, []).append(line_no)

        consumed: dict[str, int] = {}
        for elem in self.tree.iter():
            local = _local_name(elem.tag)
            if local in tag_line_map:
                idx = consumed.get(local, 0)
                line_list = tag_line_map[local]
                if idx < len(line_list):
                    self._line_of_id[id(elem)] = line_list[idx]
                    consumed[local] = idx + 1
                else:
                    self._line_of_id[id(elem)] = line_list[-1]
            else:
                self._line_of_id[id(elem)] = 0
