"""Lint engine: builds a LintDocument, dispatches to applicable rules.

The engine is a thin orchestrator over two seams:

- :class:`LintDocument` owns parsing + line mapping + traversal helpers.
- The module-level rule registry in :mod:`rule` owns rule discovery via
  the ``@rule(...)`` decorator. Rules declare ``applies_to`` so XAML and
  coded-workflow rules can share one registry.

A legacy ``register_rule(fn)`` API is retained so plugins (which were
written against the old ``(root, ns) -> list[LintIssue]`` callable shape)
keep working.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from collections.abc import Callable

# Side-effect imports: registering all built-in rules into the registry.
import rpa_architect.xaml_lint.rules_best_practices  # noqa: F401
import rpa_architect.xaml_lint.rules_coded  # noqa: F401
import rpa_architect.xaml_lint.rules_hallucination  # noqa: F401
import rpa_architect.xaml_lint.rules_security  # noqa: F401
from rpa_architect.xaml_lint.lint_document import LintDocument
from rpa_architect.xaml_lint.models import LintCategory, LintIssue, LintSeverity
from rpa_architect.xaml_lint.rule import (
    ContentKind,
    Rule,
    all_rules,
    rules_for,
)

logger = logging.getLogger(__name__)


LegacyRuleFn = Callable[[ET.Element, dict[str, str]], list[LintIssue]]


class LintEngine:
    """XAML lint engine that runs registered rules against a LintDocument.

    Built-in rules are auto-registered via the ``@rule(...)`` decorator.
    Callers can also register additional rules via :meth:`register_rule`
    (legacy ``(root, ns)`` shape) or :meth:`register` (new ``Rule`` object).
    """

    def __init__(self, *, include_default: bool = False) -> None:
        """``include_default=False`` (default) starts with an empty rule set,
        matching the historical ``LintEngine()`` contract. Use
        :func:`create_default_engine` to get an engine pre-loaded with the
        registry's built-in rules.
        """
        self._extras: list[Rule] = []
        self._include_default = include_default

    # ─────────── registration ───────────

    def register(self, rule: Rule) -> None:
        """Add a Rule (new contract) to this engine instance only.

        For globally registered rules, use the ``@rule(...)`` decorator
        in :mod:`rpa_architect.xaml_lint.rule`.
        """
        self._extras.append(rule)

    def register_rule(self, fn: LegacyRuleFn) -> None:
        """Register a legacy ``(root, ns) -> list[LintIssue]`` callable.

        Wraps the callable in a :class:`Rule` so it joins the same
        dispatch path as decorator-registered rules. Plugin authors
        keep their old signature.
        """
        wrapped = _wrap_legacy(fn)
        self._extras.append(wrapped)

    @property
    def rule_count(self) -> int:
        """Number of rules this engine will run (default + extras)."""
        return len(self._all()) if self._include_default else len(self._extras)

    # ─────────── execution ───────────

    def run(self, xml_content: str) -> list[LintIssue]:
        """Parse *xml_content* as XAML and run every applicable rule.

        Returns a flat list of issues. If parsing fails, a single
        ``XL-PARSE`` issue is returned and no rules execute.
        """
        doc = LintDocument.from_xaml(xml_content)
        return self.run_document(doc)

    def run_document(self, doc: LintDocument) -> list[LintIssue]:
        """Run every applicable rule against an already-built document."""
        if doc.kind == ContentKind.XAML and doc.parse_error is not None:
            return [
                LintIssue(
                    rule_id="XL-PARSE",
                    severity=LintSeverity.ERROR,
                    category=LintCategory.HALLUCINATION,
                    message=f"XML parse error: {doc.parse_error}",
                    suggestion=(
                        "Fix the XML syntax error before linting.  Common LLM mistakes "
                        "include unclosed tags, mismatched namespaces, and invalid characters."
                    ),
                )
            ]

        issues: list[LintIssue] = []
        for rule in self._all():
            if rule.applies_to != doc.kind:
                continue
            try:
                issues.extend(rule.check(doc))
            except Exception as exc:  # noqa: BLE001 -- rules must not crash the engine
                logger.warning("Lint rule %s raised: %s", rule.name, exc)
                issues.append(
                    LintIssue(
                        rule_id="XL-INTERNAL",
                        severity=LintSeverity.WARNING,
                        category=LintCategory.HALLUCINATION,
                        message=f"Rule '{rule.name}' raised an exception: {exc}",
                        suggestion="This is an internal linter error. Please report it.",
                    )
                )
        return issues

    # ─────────── internal ───────────

    def _all(self) -> list[Rule]:
        """Default-registry rules (if enabled) plus per-engine extras."""
        if self._include_default:
            return all_rules() + self._extras
        return list(self._extras)


def _wrap_legacy(fn: LegacyRuleFn) -> Rule:
    """Adapt a legacy ``(root, ns)`` callable to the new ``Rule`` shape."""

    def _check(doc: LintDocument) -> list[LintIssue]:
        if doc.tree is None:
            return []
        return fn(doc.tree, doc.namespaces)

    _check.__name__ = fn.__name__
    return Rule(
        id=f"legacy:{fn.__name__}",
        severity=LintSeverity.WARNING,
        category=LintCategory.HALLUCINATION,
        applies_to=ContentKind.XAML,
        check=_check,
    )


def create_default_engine() -> LintEngine:
    """Create a LintEngine with all decorator-registered rules.

    Built-in rules are pulled from the module-level registry; the engine
    will run them all (filtered by ``applies_to`` per document).
    """
    return LintEngine(include_default=True)


_default_engine: LintEngine | None = None


def get_default_engine() -> LintEngine:
    """Return a process-wide singleton engine.

    Plugins call ``get_default_engine().register_rule(fn)`` to add
    rules that persist for the lifetime of the process.
    """
    global _default_engine
    if _default_engine is None:
        _default_engine = create_default_engine()
    return _default_engine


# ─────────── back-compat re-exports for callers that imported these names ───────────
__all__ = [
    "ContentKind",
    "LintEngine",
    "Rule",
    "create_default_engine",
    "get_default_engine",
    "rules_for",
]
