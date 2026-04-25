"""XAML Hallucination Linter -- detects mistakes LLMs make when generating UiPath XAML.

Public API
----------
- ``lint_xaml(content)`` -- lint a single XAML string
- ``lint_project(project_dir)`` -- lint all XAML files in a project directory

Extension API
-------------
- ``@rule(...)`` decorator from :mod:`rpa_architect.xaml_lint.rule`
- :class:`LintDocument` from :mod:`rpa_architect.xaml_lint.lint_document`
- :class:`ContentKind` for ``applies_to`` (XAML or CODED)
"""

from __future__ import annotations

from pathlib import Path

from rpa_architect.xaml_lint.engine import (
    LintEngine,
    get_default_engine,
)
from rpa_architect.xaml_lint.lint_document import LintDocument
from rpa_architect.xaml_lint.models import (
    LintCategory,
    LintIssue,
    LintResult,
    LintSeverity,
)
from rpa_architect.xaml_lint.rule import ContentKind, Rule, rule

__all__ = [
    "ContentKind",
    "LintCategory",
    "LintDocument",
    "LintEngine",
    "LintIssue",
    "LintResult",
    "LintSeverity",
    "Rule",
    "lint_project",
    "lint_xaml",
    "rule",
]


def lint_xaml(content: str) -> list[LintIssue]:
    """Lint a single XAML string and return all detected issues.

    Returns issues sorted by severity (ERROR first), then rule_id, then line.
    """
    engine = get_default_engine()
    issues = engine.run(content)

    severity_order = {LintSeverity.ERROR: 0, LintSeverity.WARNING: 1, LintSeverity.INFO: 2}
    issues.sort(key=lambda i: (severity_order.get(i.severity, 3), i.rule_id, i.line_number))

    return issues


def lint_project(project_dir: Path) -> list[LintResult]:
    """Lint all XAML files in a UiPath project directory."""
    project_dir = Path(project_dir)
    results: list[LintResult] = []

    if not project_dir.is_dir():
        results.append(
            LintResult(
                file_path=str(project_dir),
                issues=[
                    LintIssue(
                        rule_id="XL-IO",
                        severity=LintSeverity.ERROR,
                        category=LintCategory.HALLUCINATION,
                        message=f"Project directory does not exist: {project_dir}",
                        suggestion="Verify the project path is correct.",
                    )
                ],
            )
        )
        return results

    xaml_files = sorted(project_dir.rglob("*.xaml"))

    if not xaml_files:
        results.append(
            LintResult(
                file_path=str(project_dir),
                issues=[
                    LintIssue(
                        rule_id="XL-IO",
                        severity=LintSeverity.WARNING,
                        category=LintCategory.HALLUCINATION,
                        message=f"No .xaml files found in {project_dir}",
                        suggestion="Check that the path points to a UiPath project directory.",
                    )
                ],
            )
        )
        return results

    for xaml_path in xaml_files:
        try:
            content = xaml_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            results.append(
                LintResult(
                    file_path=str(xaml_path),
                    issues=[
                        LintIssue(
                            rule_id="XL-IO",
                            severity=LintSeverity.ERROR,
                            category=LintCategory.HALLUCINATION,
                            message=f"Failed to read file: {exc}",
                            suggestion="Check file permissions and encoding (expected UTF-8).",
                        )
                    ],
                )
            )
            continue

        issues = lint_xaml(content)
        results.append(LintResult(file_path=str(xaml_path), issues=issues))

    return results
