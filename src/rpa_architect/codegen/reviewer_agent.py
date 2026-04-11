"""Code review agent — checks generated code for UiPath best practices."""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ReviewIssue(BaseModel):
    """A single review finding."""

    rule: str
    """Short rule identifier (e.g. 'NAMING-001')."""
    severity: str = "warning"
    """One of: error, warning, info."""
    message: str
    """Human-readable description."""
    line: int | None = None
    """Approximate line number (1-based), if applicable."""
    suggestion: str = ""
    """Suggested fix text."""


class ReviewResult(BaseModel):
    """Aggregate review result for one file."""

    file_path: str
    issues: list[ReviewIssue] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    approved: bool = True


# ---------------------------------------------------------------------------
# Individual review rules
# ---------------------------------------------------------------------------

def _check_naming_conventions(content: str, file_path: str) -> list[ReviewIssue]:
    """Verify PascalCase class/method names and camelCase locals."""
    issues: list[ReviewIssue] = []

    # Classes should be PascalCase
    for match in re.finditer(r"(?:public|internal|private)\s+class\s+(\w+)", content):
        name = match.group(1)
        if name[0].islower():
            issues.append(
                ReviewIssue(
                    rule="NAMING-001",
                    severity="warning",
                    message=f"Class '{name}' should use PascalCase.",
                    suggestion=f"Rename to '{name[0].upper()}{name[1:]}'.",
                )
            )

    # Public methods should be PascalCase
    for match in re.finditer(r"(?:public|protected)\s+(?:async\s+)?[\w<>\[\]]+\s+(\w+)\s*\(", content):
        name = match.group(1)
        if name[0].islower() and name not in ("main", "run"):
            issues.append(
                ReviewIssue(
                    rule="NAMING-002",
                    severity="info",
                    message=f"Public method '{name}' should use PascalCase.",
                    suggestion=f"Rename to '{name[0].upper()}{name[1:]}'.",
                )
            )

    return issues


def _check_error_handling(content: str, file_path: str) -> list[ReviewIssue]:
    """Ensure try/catch blocks exist in workflow files."""
    issues: list[ReviewIssue] = []

    if file_path.endswith(".cs") and "CodedWorkflow" in content:
        if "try" not in content:
            issues.append(
                ReviewIssue(
                    rule="ERR-001",
                    severity="error",
                    message="Workflow has no try/catch blocks — unhandled exceptions will crash the robot.",
                    suggestion="Wrap main logic in try { ... } catch (Exception ex) { Log(...); throw; }.",
                )
            )
        if "catch" in content and "Log" not in content and "log" not in content:
            issues.append(
                ReviewIssue(
                    rule="ERR-002",
                    severity="warning",
                    message="Catch block does not log the exception.",
                    suggestion='Add Log(ex.Message, LogLevel.Error) inside catch blocks.',
                )
            )

    return issues


def _check_logging(content: str, file_path: str) -> list[ReviewIssue]:
    """Check for proper logging calls."""
    issues: list[ReviewIssue] = []

    if file_path.endswith(".cs") and "CodedWorkflow" in content:
        # Should have at least one Log call
        if not re.search(r"\bLog\s*\(", content):
            issues.append(
                ReviewIssue(
                    rule="LOG-001",
                    severity="warning",
                    message="Workflow contains no Log() calls — add logging for observability.",
                    suggestion='Add Log("Starting workflow...", LogLevel.Info) at entry point.',
                )
            )

    return issues


def _check_reframework_compliance(content: str, file_path: str) -> list[ReviewIssue]:
    """Check REFramework patterns in coded workflows."""
    issues: list[ReviewIssue] = []

    if file_path.endswith(".cs") and "CodedWorkflow" in content:
        # Should reference config
        if "Config" not in content and "config" not in content:
            issues.append(
                ReviewIssue(
                    rule="REF-001",
                    severity="info",
                    message="Workflow does not reference Config — ensure settings come from Config.xlsx.",
                    suggestion="Use ConfigWrapper to access Settings, Constants, and Assets.",
                )
            )

    return issues


def _check_service_injection(content: str, file_path: str) -> list[ReviewIssue]:
    """Verify UiPath services are injected via [Service] attribute."""
    issues: list[ReviewIssue] = []

    if file_path.endswith(".cs") and "CodedWorkflow" in content:
        # Check that services used in code are properly declared
        service_uses = re.findall(r"(?:_(\w+Service)\b)", content)
        for svc in set(service_uses):
            # Look for corresponding [Service] declaration
            pattern = rf"\[Service\]\s*.*\b{svc}\b"
            if not re.search(pattern, content, re.IGNORECASE):
                issues.append(
                    ReviewIssue(
                        rule="SVC-001",
                        severity="error",
                        message=f"Service field '_{svc}' used but no [Service] attribute found.",
                        suggestion=f"Add: [Service] public I{svc} _{svc} {{ get; set; }}",
                    )
                )

    return issues


def _check_async_patterns(content: str, file_path: str) -> list[ReviewIssue]:
    """Check for correct async/await usage."""
    issues: list[ReviewIssue] = []

    if file_path.endswith(".cs"):
        # Async methods should use await
        for match in re.finditer(r"public\s+async\s+Task\b.*?(\w+)\s*\(", content):
            method_name = match.group(1)
            # Rough check: find method body and see if 'await' appears
            start = match.end()
            brace_count = 0
            body_start = content.find("{", start)
            if body_start == -1:
                continue
            body = ""
            for i in range(body_start, min(body_start + 2000, len(content))):
                c = content[i]
                if c == "{":
                    brace_count += 1
                elif c == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        body = content[body_start : i + 1]
                        break

            if body and "await" not in body:
                issues.append(
                    ReviewIssue(
                        rule="ASYNC-001",
                        severity="warning",
                        message=f"Async method '{method_name}' contains no await expressions.",
                        suggestion="Either add await or remove async modifier.",
                    )
                )

    return issues


_ALL_CHECKS = [
    _check_naming_conventions,
    _check_error_handling,
    _check_logging,
    _check_reframework_compliance,
    _check_service_injection,
    _check_async_patterns,
]


def review_file(file_path: str, content: str) -> ReviewResult:
    """Run all review checks on a single file.

    Args:
        file_path: Relative path of the file.
        content: Full text content.

    Returns:
        Aggregated ReviewResult.
    """
    all_issues: list[ReviewIssue] = []
    for check_fn in _ALL_CHECKS:
        all_issues.extend(check_fn(content, file_path))

    suggestions = list({issue.suggestion for issue in all_issues if issue.suggestion})
    has_errors = any(i.severity == "error" for i in all_issues)

    return ReviewResult(
        file_path=file_path,
        issues=all_issues,
        suggestions=suggestions,
        approved=not has_errors,
    )


async def review(state: "GenerationState") -> "GenerationState":  # noqa: F821
    """Review all generated files and annotate the state with findings.

    Populates ``state.validation_results["review"]`` and appends error-level
    issues to ``state.errors``.
    """
    results: list[dict[str, Any]] = []
    review_errors: list[str] = []

    for rel_path, gen_file in state.generated_files.items():
        result = review_file(rel_path, gen_file.content)
        results.append(result.model_dump())

        for issue in result.issues:
            if issue.severity == "error":
                review_errors.append(f"[{issue.rule}] {rel_path}: {issue.message}")

    state.validation_results["review"] = results

    if review_errors:
        logger.warning("Review found %d error(s).", len(review_errors))
        state.errors.extend(review_errors)
    else:
        logger.info("Review passed — %d files checked.", len(results))

    return state
