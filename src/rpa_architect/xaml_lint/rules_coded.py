"""Lint rules for C# coded workflow files.

Four regex-based rules that operate on raw C# source text (not XML).
"""

from __future__ import annotations

import re

from rpa_architect.xaml_lint.models import LintCategory, LintIssue, LintSeverity

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ORCHESTRATOR_URL_RE = re.compile(
    r"https?://[^\s\"']*(?:orchestrator|uipath\.com/api)", re.IGNORECASE
)

_UNSAFE_CREDENTIAL_RE = re.compile(
    r"""(?:string\s+password|var\s+password\s*=\s*\")""", re.IGNORECASE
)

_WORKFLOW_ATTR_RE = re.compile(r"\[\s*Workflow\s*\]")

_CODED_WORKFLOW_CLASS_RE = re.compile(r":\s*CodedWorkflow\b")

_USING_CODED_WORKFLOWS_RE = re.compile(
    r"using\s+UiPath\.CodedWorkflows\s*;"
)


# ---------------------------------------------------------------------------
# Individual rule checks
# ---------------------------------------------------------------------------


def _check_missing_workflow_attribute(content: str) -> list[LintIssue]:
    """XL-C001: Class extends CodedWorkflow but no [Workflow] attribute."""
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


def _check_hardcoded_orchestrator_url(content: str) -> list[LintIssue]:
    """XL-C002: Hardcoded Orchestrator URL detected."""
    issues: list[LintIssue] = []
    for match in _ORCHESTRATOR_URL_RE.finditer(content):
        line_no = content[:match.start()].count("\n") + 1
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


def _check_missing_using_directives(content: str) -> list[LintIssue]:
    """XL-C003: File references CodedWorkflow but missing using directive."""
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


def _check_unsafe_credential_handling(content: str) -> list[LintIssue]:
    """XL-C004: Unsafe credential handling detected."""
    issues: list[LintIssue] = []
    for match in _UNSAFE_CREDENTIAL_RE.finditer(content):
        line_no = content[:match.start()].count("\n") + 1
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
# Public API
# ---------------------------------------------------------------------------


def lint_coded_file(content: str, file_path: str = "") -> list[LintIssue]:
    """Run all coded workflow lint rules on a C# file content string.

    Parameters
    ----------
    content:
        Raw C# source code.
    file_path:
        Optional file path (used only for diagnostics).

    Returns
    -------
    list[LintIssue]
        All issues found across all four rules.
    """
    issues: list[LintIssue] = []
    issues.extend(_check_missing_workflow_attribute(content))
    issues.extend(_check_hardcoded_orchestrator_url(content))
    issues.extend(_check_missing_using_directives(content))
    issues.extend(_check_unsafe_credential_handling(content))
    return issues
