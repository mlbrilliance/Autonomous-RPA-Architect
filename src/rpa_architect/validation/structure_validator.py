"""REFramework project structure validator."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ValidationIssue(BaseModel):
    """A single structural validation finding."""

    severity: str = "error"
    """One of: error, warning, info."""
    category: str = ""
    """Category: 'file', 'config', 'structure'."""
    message: str
    """Human-readable description."""
    path: str = ""
    """File path related to the issue, if any."""


# ---------------------------------------------------------------------------
# Expected REFramework files
# ---------------------------------------------------------------------------

_REQUIRED_FILES: list[tuple[str, str]] = [
    ("project.json", "Project manifest is missing."),
]

_RECOMMENDED_FILES: list[tuple[str, str]] = [
    ("Main.xaml", "Main.xaml entry-point workflow is missing."),
    ("Process.xaml", "Process.xaml business logic workflow is missing (REFramework)."),
]

_REFRAMEWORK_FILES: list[tuple[str, str]] = [
    ("Framework/InitAllSettings.xaml", "REFramework InitAllSettings.xaml is missing."),
    ("Framework/GetTransactionData.xaml", "REFramework GetTransactionData.xaml is missing."),
    ("Framework/ProcessTransaction.xaml", "REFramework ProcessTransaction.xaml is missing."),
    ("Framework/SetTransactionStatus.xaml", "REFramework SetTransactionStatus.xaml is missing."),
    ("Framework/InitAllApplications.xaml", "REFramework InitAllApplications.xaml is missing."),
    ("Framework/CloseAllApplications.xaml", "REFramework CloseAllApplications.xaml is missing."),
    ("Framework/KillAllProcesses.xaml", "REFramework KillAllProcesses.xaml is missing."),
]

_CONFIG_REQUIRED_SHEETS = {"Settings", "Constants", "Assets"}


def _check_required_files(project_dir: Path) -> list[ValidationIssue]:
    """Check that essential project files exist."""
    issues: list[ValidationIssue] = []

    for rel_path, message in _REQUIRED_FILES:
        if not (project_dir / rel_path).is_file():
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="file",
                    message=message,
                    path=rel_path,
                )
            )

    for rel_path, message in _RECOMMENDED_FILES:
        if not (project_dir / rel_path).is_file():
            # For coded workflows, Main.xaml and Process.xaml are optional
            # if there are .cs files instead
            cs_files = list(project_dir.rglob("*.cs"))
            if cs_files:
                issues.append(
                    ValidationIssue(
                        severity="info",
                        category="file",
                        message=f"{message} (coded workflows detected — may be intentional).",
                        path=rel_path,
                    )
                )
            else:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        category="file",
                        message=message,
                        path=rel_path,
                    )
                )

    return issues


def _check_reframework_structure(project_dir: Path) -> list[ValidationIssue]:
    """Check for REFramework-specific workflow files."""
    issues: list[ValidationIssue] = []

    # Only check if there's a Framework/ directory or if project looks like REFramework
    framework_dir = project_dir / "Framework"
    if not framework_dir.is_dir():
        # Not an error if using coded workflows
        cs_files = list(project_dir.rglob("*.cs"))
        if not cs_files:
            issues.append(
                ValidationIssue(
                    severity="info",
                    category="structure",
                    message="No Framework/ directory found — project may not use REFramework.",
                )
            )
        return issues

    for rel_path, message in _REFRAMEWORK_FILES:
        if not (project_dir / rel_path).is_file():
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="structure",
                    message=message,
                    path=rel_path,
                )
            )

    return issues


def _check_project_json(project_dir: Path) -> list[ValidationIssue]:
    """Validate project.json contents."""
    issues: list[ValidationIssue] = []
    project_json_path = project_dir / "project.json"

    if not project_json_path.is_file():
        return issues  # Already reported by _check_required_files

    try:
        data = json.loads(project_json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        issues.append(
            ValidationIssue(
                severity="error",
                category="config",
                message=f"project.json is not valid JSON: {exc}",
                path="project.json",
            )
        )
        return issues

    # Required fields
    for field in ("name", "main", "dependencies"):
        if field not in data:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="config",
                    message=f"project.json missing recommended field: '{field}'.",
                    path="project.json",
                )
            )

    # Check expression language
    expr_lang = data.get("expressionLanguage", "")
    if expr_lang and expr_lang not in ("CSharp", "VB"):
        issues.append(
            ValidationIssue(
                severity="warning",
                category="config",
                message=f"Unusual expressionLanguage: '{expr_lang}' (expected 'CSharp' or 'VB').",
                path="project.json",
            )
        )

    return issues


def _check_config_xlsx(project_dir: Path) -> list[ValidationIssue]:
    """Validate Config.xlsx has the required REFramework sheets."""
    issues: list[ValidationIssue] = []

    # Look for Config.xlsx in common locations
    config_paths = [
        project_dir / "Data" / "Config.xlsx",
        project_dir / "Config.xlsx",
        project_dir / "data" / "Config.xlsx",
    ]

    config_path: Path | None = None
    for p in config_paths:
        if p.is_file():
            config_path = p
            break

    if config_path is None:
        issues.append(
            ValidationIssue(
                severity="info",
                category="config",
                message="Config.xlsx not found — REFramework configuration may be missing.",
            )
        )
        return issues

    try:
        import openpyxl

        wb = openpyxl.load_workbook(str(config_path), read_only=True, data_only=True)
        sheet_names = set(wb.sheetnames)
        wb.close()

        missing_sheets = _CONFIG_REQUIRED_SHEETS - sheet_names
        if missing_sheets:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="config",
                    message=f"Config.xlsx missing required sheets: {', '.join(sorted(missing_sheets))}.",
                    path=str(config_path.relative_to(project_dir)),
                )
            )
    except ImportError:
        logger.debug("openpyxl not available — skipping Config.xlsx sheet validation.")
    except Exception as exc:
        issues.append(
            ValidationIssue(
                severity="warning",
                category="config",
                message=f"Could not read Config.xlsx: {exc}",
                path=str(config_path.relative_to(project_dir)),
            )
        )

    return issues


def _check_config_driven_architecture(project_dir: Path) -> list[ValidationIssue]:
    """Check that values that should be config-driven are not hardcoded.

    Inspired by the uipath-ai-skills lint rules — enforce that URLs,
    credentials, and queue names come from Config.xlsx rather than
    being embedded in workflow code.
    """
    import re

    issues: list[ValidationIssue] = []
    url_pattern = re.compile(r'https?://[^\s"<>]+', re.IGNORECASE)
    credential_pattern = re.compile(
        r'(?:password|pwd|secret|apikey|api_key|token)\s*=\s*"[^"]+',
        re.IGNORECASE,
    )

    # Scan all .cs and .xaml files (excluding framework templates)
    for ext in ("*.cs", "*.xaml"):
        for file_path in project_dir.rglob(ext):
            rel = str(file_path.relative_to(project_dir))
            # Skip framework files — they legitimately reference Config
            if rel.startswith("Framework/") or ".objects/" in rel:
                continue
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            # Check for hardcoded URLs
            for match in url_pattern.finditer(content):
                url = match.group()
                # Ignore common non-actionable URLs (xmlns, schemas, etc.)
                if any(skip in url for skip in (
                    "schemas.microsoft.com", "schemas.uipath.com",
                    "schemas.openxmlformats.org", "www.w3.org",
                    "xmlns", "//localhost",
                )):
                    continue
                issues.append(
                    ValidationIssue(
                        severity="info",
                        category="config",
                        message=(
                            f"Hardcoded URL found: '{url[:60]}...' — "
                            "consider moving to Config.xlsx Constants sheet."
                        ),
                        path=rel,
                    )
                )
                break  # One warning per file is enough

            # Check for hardcoded credentials
            for match in credential_pattern.finditer(content):
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        category="config",
                        message=(
                            "Possible hardcoded credential found — "
                            "use GetRobotCredential or Orchestrator assets instead."
                        ),
                        path=rel,
                    )
                )
                break

    return issues


def validate_structure(project_dir: Path) -> list[ValidationIssue]:
    """Run all structural validation checks on a UiPath project directory.

    Args:
        project_dir: Root directory of the UiPath project.

    Returns:
        List of validation issues (may be empty if everything looks good).
    """
    project_dir = Path(project_dir)
    if not project_dir.is_dir():
        return [
            ValidationIssue(
                severity="error",
                category="structure",
                message=f"Project directory does not exist: {project_dir}",
            )
        ]

    issues: list[ValidationIssue] = []
    issues.extend(_check_required_files(project_dir))
    issues.extend(_check_project_json(project_dir))
    issues.extend(_check_reframework_structure(project_dir))
    issues.extend(_check_config_xlsx(project_dir))
    issues.extend(_check_config_driven_architecture(project_dir))

    logger.info(
        "Structure validation: %d issue(s) (%d errors, %d warnings).",
        len(issues),
        sum(1 for i in issues if i.severity == "error"),
        sum(1 for i in issues if i.severity == "warning"),
    )
    return issues
