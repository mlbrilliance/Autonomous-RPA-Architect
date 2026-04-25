"""Lint rules for C# coded workflow files.

Four regex-based rules that operate on raw C# source text. Registered
with ``applies_to=ContentKind.CODED`` so the engine dispatches them only
to coded documents.
"""

from __future__ import annotations

import re

from rpa_architect.xaml_lint.lint_document import LintDocument
from rpa_architect.xaml_lint.models import LintCategory, LintIssue, LintSeverity
from rpa_architect.xaml_lint.rule import ContentKind, rule

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_ORCHESTRATOR_URL_RE = re.compile(
    r"https?://[^\s\"']*(?:orchestrator|uipath\.com/api)", re.IGNORECASE
)

_UNSAFE_CREDENTIAL_RE = re.compile(
    r"""(?:string\s+password|var\s+password\s*=\s*\")""", re.IGNORECASE
)

_WORKFLOW_ATTR_RE = re.compile(r"\[\s*Workflow\s*\]")

_CODED_WORKFLOW_CLASS_RE = re.compile(r":\s*CodedWorkflow\b")

_USING_CODED_WORKFLOWS_RE = re.compile(r"using\s+UiPath\.CodedWorkflows\s*;")


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


@rule(
    id="XL-C001",
    severity=LintSeverity.ERROR,
    category=LintCategory.BEST_PRACTICE,
    applies_to=ContentKind.CODED,
)
def lint_missing_workflow_attribute(doc: LintDocument) -> list[LintIssue]:
    """XL-C001: Class extends CodedWorkflow but no [Workflow] attribute."""
    content = doc.source_text
    if not _CODED_WORKFLOW_CLASS_RE.search(content):
        return []
    if _WORKFLOW_ATTR_RE.search(content):
        return []
    return [
        LintIssue(
            rule_id="XL-C001",
            severity=LintSeverity.ERROR,
            category=LintCategory.BEST_PRACTICE,
            message="Class extends CodedWorkflow but no [Workflow] attribute found on any method.",
            suggestion="Add [Workflow] attribute to the main workflow method.",
        )
    ]


@rule(
    id="XL-C002",
    severity=LintSeverity.WARNING,
    category=LintCategory.CONFIG,
    applies_to=ContentKind.CODED,
)
def lint_hardcoded_orchestrator_url(doc: LintDocument) -> list[LintIssue]:
    """XL-C002: Hardcoded Orchestrator URL detected."""
    content = doc.source_text
    issues: list[LintIssue] = []
    for match in _ORCHESTRATOR_URL_RE.finditer(content):
        line_no = content[: match.start()].count("\n") + 1
        issues.append(
            LintIssue(
                rule_id="XL-C002",
                severity=LintSeverity.WARNING,
                category=LintCategory.CONFIG,
                message=f"Hardcoded Orchestrator URL detected: {match.group()!r}",
                line_number=line_no,
                suggestion="Use configuration or environment variables for Orchestrator URLs.",
            )
        )
    return issues


@rule(
    id="XL-C003",
    severity=LintSeverity.ERROR,
    category=LintCategory.NAMESPACE,
    applies_to=ContentKind.CODED,
)
def lint_missing_using_directives(doc: LintDocument) -> list[LintIssue]:
    """XL-C003: File references CodedWorkflow but missing using directive."""
    content = doc.source_text
    if not _CODED_WORKFLOW_CLASS_RE.search(content):
        return []
    if _USING_CODED_WORKFLOWS_RE.search(content):
        return []
    return [
        LintIssue(
            rule_id="XL-C003",
            severity=LintSeverity.ERROR,
            category=LintCategory.NAMESPACE,
            message="File references CodedWorkflow but missing 'using UiPath.CodedWorkflows'.",
            suggestion="Add 'using UiPath.CodedWorkflows;' to the top of the file.",
        )
    ]


@rule(
    id="XL-C004",
    severity=LintSeverity.WARNING,
    category=LintCategory.CREDENTIAL,
    applies_to=ContentKind.CODED,
)
def lint_unsafe_credential_handling(doc: LintDocument) -> list[LintIssue]:
    """XL-C004: Unsafe credential handling detected."""
    content = doc.source_text
    issues: list[LintIssue] = []
    for match in _UNSAFE_CREDENTIAL_RE.finditer(content):
        line_no = content[: match.start()].count("\n") + 1
        issues.append(
            LintIssue(
                rule_id="XL-C004",
                severity=LintSeverity.WARNING,
                category=LintCategory.CREDENTIAL,
                message=f"Unsafe credential handling detected: {match.group()!r}",
                line_number=line_no,
                suggestion="Use SecureString or Orchestrator Credential assets instead.",
            )
        )
    return issues


# ---------------------------------------------------------------------------
# Public API — backwards-compat wrapper for callers that use lint_coded_file
# directly (cli.py, tests/test_validation/test_coded_lint.py). Internally
# this builds a CODED LintDocument and runs the engine, so the same rules
# fire whether you call lint_coded_file() or lint_xaml() / lint_project().
# ---------------------------------------------------------------------------


def lint_coded_file(content: str, file_path: str = "") -> list[LintIssue]:
    """Run all coded-workflow lint rules on a C# file content string."""
    from rpa_architect.xaml_lint.engine import get_default_engine

    doc = LintDocument.from_coded(content)
    return get_default_engine().run_document(doc)


# ─────────── legacy per-rule helpers (kept for backwards-compat) ───────────
# Tests in tests/test_validation/test_coded_lint.py call these private
# helpers directly with raw content. They each adapt the (content) shape
# to the new (doc) shape so the rule body remains the single source of truth.


def _check_missing_workflow_attribute(content: str) -> list[LintIssue]:
    return lint_missing_workflow_attribute(LintDocument.from_coded(content))


def _check_hardcoded_orchestrator_url(content: str) -> list[LintIssue]:
    return lint_hardcoded_orchestrator_url(LintDocument.from_coded(content))


def _check_missing_using_directives(content: str) -> list[LintIssue]:
    return lint_missing_using_directives(LintDocument.from_coded(content))


def _check_unsafe_credential_handling(content: str) -> list[LintIssue]:
    return lint_unsafe_credential_handling(LintDocument.from_coded(content))
