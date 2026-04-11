"""XAML Hallucination Linter -- detects mistakes LLMs make when generating UiPath XAML.

Public API
----------
- ``lint_xaml(content)`` -- lint a single XAML string
- ``lint_project(project_dir)`` -- lint all XAML files in a project directory
"""

from __future__ import annotations

from pathlib import Path

from rpa_architect.xaml_lint.engine import LintEngine, create_default_engine
from rpa_architect.xaml_lint.models import (
    LintCategory,
    LintIssue,
    LintResult,
    LintSeverity,
)

__all__ = [
    "LintCategory",
    "LintEngine",
    "LintIssue",
    "LintResult",
    "LintSeverity",
    "lint_project",
    "lint_xaml",
]

# Module-level default engine (lazy singleton)
_default_engine: LintEngine | None = None


def _get_engine() -> LintEngine:
    global _default_engine  # noqa: PLW0603
    if _default_engine is None:
        _default_engine = create_default_engine()
    return _default_engine


def lint_xaml(content: str) -> list[LintIssue]:
    """Lint a single XAML string and return all detected issues.

    Parameters
    ----------
    content:
        Raw XAML content as a string.

    Returns
    -------
    list[LintIssue]
        All lint issues found, sorted by severity (ERROR first) then rule_id.
    """
    engine = _get_engine()
    issues = engine.run(content)

    # Sort: errors first, then warnings, then info
    severity_order = {LintSeverity.ERROR: 0, LintSeverity.WARNING: 1, LintSeverity.INFO: 2}
    issues.sort(key=lambda i: (severity_order.get(i.severity, 3), i.rule_id, i.line_number))

    return issues


def lint_project(project_dir: Path) -> list[LintResult]:
    """Lint all XAML files in a UiPath project directory.

    Parameters
    ----------
    project_dir:
        Path to the UiPath project root directory.  All ``*.xaml`` files
        found recursively will be linted.

    Returns
    -------
    list[LintResult]
        One ``LintResult`` per XAML file, including the file path and all
        issues found.
    """
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
        results.append(
            LintResult(
                file_path=str(xaml_path),
                issues=issues,
            )
        )

    return results
