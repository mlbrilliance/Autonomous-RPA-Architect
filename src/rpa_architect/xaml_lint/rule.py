"""Rule contract: decorator, dataclass, and module-level registry.

Rules are functions that take a :class:`LintDocument` and return a list of
:class:`LintIssue`. The ``@rule(...)`` decorator attaches metadata
(``id``, ``severity``, ``category``, ``applies_to``) and registers the
function in a module-level registry. The engine dispatches by
``applies_to`` so XAML rules and coded-workflow rules share one registry.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from rpa_architect.xaml_lint.models import LintCategory, LintIssue, LintSeverity

if TYPE_CHECKING:
    from rpa_architect.xaml_lint.lint_document import LintDocument


class ContentKind(str, Enum):
    """What kind of content a Rule applies to.

    XAML rules read the parsed element tree; CODED rules read the raw
    C# source string. The engine dispatches by this field.
    """

    XAML = "xaml"
    CODED = "coded"


RuleFn = Callable[["LintDocument"], list[LintIssue]]


@dataclass(frozen=True)
class Rule:
    """A registered lint rule.

    ``check`` is the implementation function; the engine wraps the
    per-rule try/except around it so a buggy rule cannot crash the run.
    """

    id: str
    severity: LintSeverity
    category: LintCategory
    applies_to: ContentKind
    check: RuleFn

    @property
    def name(self) -> str:
        return self.check.__name__


_REGISTRY: list[Rule] = []


def rule(
    *,
    id: str,
    severity: LintSeverity,
    category: LintCategory,
    applies_to: ContentKind = ContentKind.XAML,
) -> Callable[[RuleFn], RuleFn]:
    """Decorator: register a rule function in the module-level registry.

    The decorated function must take ``(doc: LintDocument)`` and return
    ``list[LintIssue]``. The decorator returns the function unchanged so
    callers can still invoke it directly (useful for unit tests).
    """

    def decorator(fn: RuleFn) -> RuleFn:
        _REGISTRY.append(
            Rule(
                id=id,
                severity=severity,
                category=category,
                applies_to=applies_to,
                check=fn,
            )
        )
        return fn

    return decorator


def all_rules() -> list[Rule]:
    """Return a snapshot of every registered rule.

    Returned list is a copy — mutating it does not affect the registry.
    """
    return list(_REGISTRY)


def rules_for(kind: ContentKind) -> list[Rule]:
    """Return registered rules whose ``applies_to`` matches ``kind``."""
    return [r for r in _REGISTRY if r.applies_to == kind]
