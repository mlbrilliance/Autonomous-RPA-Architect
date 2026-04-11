"""Lint engine: parses XAML, runs registered rules, collects issues.

The engine automatically registers all rules from the hallucination,
security, and best-practice modules on import.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from typing import TYPE_CHECKING

from rpa_architect.xaml_lint._line_map import clear as _clear_line_map
from rpa_architect.xaml_lint._line_map import get_line_number, set_line_number
from rpa_architect.xaml_lint.models import LintCategory, LintIssue, LintSeverity
from rpa_architect.xaml_lint.rules_best_practices import ALL_BEST_PRACTICE_RULES
from rpa_architect.xaml_lint.rules_hallucination import ALL_HALLUCINATION_RULES
from rpa_architect.xaml_lint.rules_security import ALL_SECURITY_RULES

if TYPE_CHECKING:
    pass

# Type alias for a lint rule function
RuleFunction = Callable[[ET.Element, dict[str, str]], list[LintIssue]]


class LintEngine:
    """XAML lint engine that maintains a list of rule functions and runs them
    against parsed XML content.

    Usage::

        engine = LintEngine()
        issues = engine.run("<Activity ...> ... </Activity>")
    """

    def __init__(self) -> None:
        self._rules: list[RuleFunction] = []

    def register_rule(self, fn: RuleFunction) -> None:
        """Add a rule function to the engine.

        A rule function must accept (root: ET.Element, ns: dict[str, str])
        and return a list[LintIssue].
        """
        self._rules.append(fn)

    @property
    def rule_count(self) -> int:
        """Number of registered rules."""
        return len(self._rules)

    def run(self, xml_content: str) -> list[LintIssue]:
        """Parse *xml_content* as XML and run all registered rules.

        Returns a list of :class:`LintIssue` instances.  If the XML cannot
        be parsed, a single ERROR issue is returned describing the parse error.
        """
        # Clear stale line numbers from previous runs
        _clear_line_map()

        # ── Parse XML ─────────────────────────────────────────────────
        root: ET.Element
        namespaces: dict[str, str]

        try:
            root, namespaces = self._parse_xml(xml_content)
        except ET.ParseError as exc:
            return [
                LintIssue(
                    rule_id="XL-PARSE",
                    severity=LintSeverity.ERROR,
                    category=LintCategory.HALLUCINATION,
                    message=f"XML parse error: {exc}",
                    suggestion=(
                        "Fix the XML syntax error before linting.  Common LLM mistakes include "
                        "unclosed tags, mismatched namespaces, and invalid characters."
                    ),
                )
            ]

        # ── Run rules ─────────────────────────────────────────────────
        all_issues: list[LintIssue] = []

        for rule_fn in self._rules:
            try:
                issues = rule_fn(root, namespaces)
                all_issues.extend(issues)
            except Exception as exc:  # noqa: BLE001 -- rules should not crash the engine
                all_issues.append(
                    LintIssue(
                        rule_id="XL-INTERNAL",
                        severity=LintSeverity.WARNING,
                        category=LintCategory.HALLUCINATION,
                        message=f"Rule '{rule_fn.__name__}' raised an exception: {exc}",
                        suggestion="This is an internal linter error. Please report it.",
                    )
                )

        return all_issues

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_xml(xml_content: str) -> tuple[ET.Element, dict[str, str]]:
        """Parse XML content and extract namespace declarations."""
        namespaces: dict[str, str] = {}

        # Extract namespace declarations from raw text
        # (ElementTree normalizes them away from attribute access)
        for match in re.finditer(r'xmlns(?::(\w+))?=["\']([^"\']+)["\']', xml_content):
            prefix = match.group(1) or ""
            uri = match.group(2)
            namespaces[prefix] = uri

        # Parse the XML
        tree_builder = ET.XMLParser()
        tree_builder.feed(xml_content)
        root = tree_builder.close()

        # Populate the shared line-number map
        _attach_line_numbers(root, xml_content)

        return root, namespaces


def _attach_line_numbers(root: ET.Element, xml_content: str) -> None:
    """Best-effort population of the shared line-number map for all elements.

    ElementTree doesn't natively track source positions, so we use a
    heuristic: for each element, search for its tag in the source text
    and record the line number of the first unmatched occurrence.
    """
    lines = xml_content.split("\n")

    # Build a simple index: for each local tag name, which lines does it appear on?
    tag_line_map: dict[str, list[int]] = {}
    for line_no, line_text in enumerate(lines, start=1):
        for m in re.finditer(r"<([A-Za-z_][\w:.]*)", line_text):
            tag = m.group(1)
            local = tag.split(":")[-1] if ":" in tag else tag
            tag_line_map.setdefault(local, []).append(line_no)

    # Walk elements in document order and assign the next available line
    consumed: dict[str, int] = {}

    for elem in root.iter():
        tag = elem.tag
        if tag.startswith("{"):
            local = tag.split("}", 1)[1]
        else:
            local = tag

        if local in tag_line_map:
            idx = consumed.get(local, 0)
            line_list = tag_line_map[local]
            if idx < len(line_list):
                set_line_number(elem, line_list[idx])
                consumed[local] = idx + 1
            else:
                set_line_number(elem, line_list[-1])
        else:
            set_line_number(elem, 0)


def create_default_engine() -> LintEngine:
    """Create a LintEngine with all built-in rules registered."""
    engine = LintEngine()

    for rule_fn in ALL_HALLUCINATION_RULES:
        engine.register_rule(rule_fn)

    for rule_fn in ALL_SECURITY_RULES:
        engine.register_rule(rule_fn)

    for rule_fn in ALL_BEST_PRACTICE_RULES:
        engine.register_rule(rule_fn)

    return engine


# Module-level singleton for the default engine
_default_engine: LintEngine | None = None


def get_default_engine() -> LintEngine:
    """Return a module-level singleton ``LintEngine`` with all built-in rules.

    The engine is created lazily on first call.  Subsequent calls return the
    same instance, which allows plugins to register additional rules that
    persist for the lifetime of the process.
    """
    global _default_engine
    if _default_engine is None:
        _default_engine = create_default_engine()
    return _default_engine
