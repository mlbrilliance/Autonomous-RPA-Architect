"""UiPath Workflow Analyzer CLI wrapper."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AnalysisFinding(BaseModel):
    """A single finding from the UiPath Workflow Analyzer."""

    rule_id: str = ""
    """Analyzer rule identifier (e.g. 'ST-NMG-001')."""
    rule_name: str = ""
    """Human-readable rule name."""
    severity: str = "warning"
    """One of: error, warning, info, verbose."""
    message: str = ""
    """Description of the finding."""
    file_path: str = ""
    """Workflow file where the issue was found."""
    recommendation: str = ""
    """Suggested remediation."""


class AnalysisResult(BaseModel):
    """Aggregated result of UiPath Workflow Analyzer execution."""

    success: bool = False
    """True if analysis completed without internal errors."""
    findings: list[AnalysisFinding] = Field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    raw_output: str = ""
    """Full CLI output."""
    analyzer_available: bool = True
    """Whether the uipath CLI was found."""


def _find_uipath_cli() -> str | None:
    """Locate the UiPath CLI executable."""
    # Check common names
    for name in ("uipath", "UiPath.Studio.CommandLine", "UiRobot"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _parse_analysis_output(raw_output: str) -> list[AnalysisFinding]:
    """Parse UiPath Workflow Analyzer output into findings.

    The analyzer can output JSON or text. We attempt JSON first,
    then fall back to line-by-line parsing.
    """
    findings: list[AnalysisFinding] = []

    # Attempt JSON parse
    try:
        data = json.loads(raw_output)
        items = data if isinstance(data, list) else data.get("results", data.get("violations", []))
        for item in items:
            if isinstance(item, dict):
                findings.append(
                    AnalysisFinding(
                        rule_id=item.get("ruleId", item.get("ErrorCode", "")),
                        rule_name=item.get("ruleName", item.get("RuleName", "")),
                        severity=item.get("severity", item.get("ErrorSeverity", "warning")).lower(),
                        message=item.get("message", item.get("Description", "")),
                        file_path=item.get("filePath", item.get("FilePath", "")),
                        recommendation=item.get("recommendation", item.get("Recommendation", "")),
                    )
                )
        return findings
    except (json.JSONDecodeError, TypeError):
        pass

    # Fallback: line-by-line text parsing
    for line in raw_output.splitlines():
        line = line.strip()
        if not line:
            continue

        # Common patterns: "ST-NMG-001: Message [file.xaml]"
        severity = "info"
        if "error" in line.lower():
            severity = "error"
        elif "warning" in line.lower() or "warn" in line.lower():
            severity = "warning"

        # Extract rule ID if present
        rule_id = ""
        import re
        rule_match = re.match(r"^([A-Z]{2}-[A-Z]{3}-\d{3})\s*[:\-]\s*(.+)", line)
        if rule_match:
            rule_id = rule_match.group(1)
            message = rule_match.group(2)
        else:
            message = line

        if message:
            findings.append(
                AnalysisFinding(
                    rule_id=rule_id,
                    severity=severity,
                    message=message,
                )
            )

    return findings


async def analyze(
    project_dir: Path,
    timeout_seconds: int = 120,
) -> AnalysisResult:
    """Run UiPath Workflow Analyzer on a project directory.

    Args:
        project_dir: Root directory of the UiPath project.
        timeout_seconds: Maximum time to wait for analysis.

    Returns:
        AnalysisResult with parsed findings.
    """
    cli_path = _find_uipath_cli()
    if cli_path is None:
        logger.info("UiPath CLI not found — skipping workflow analysis.")
        return AnalysisResult(
            success=True,  # Don't block on missing tool
            analyzer_available=False,
            raw_output="UiPath CLI not found on PATH.",
        )

    # Find the project file
    project_file: Path | None = None
    for pattern in ("project.json", "*.uiproj"):
        candidates = list(project_dir.glob(pattern))
        if candidates:
            project_file = candidates[0]
            break

    if project_file is None:
        return AnalysisResult(
            success=False,
            analyzer_available=True,
            raw_output="No project.json or .uiproj file found.",
            findings=[
                AnalysisFinding(
                    rule_id="PROJ-001",
                    severity="error",
                    message="Cannot run analysis: no project file found.",
                )
            ],
            error_count=1,
        )

    cmd = [
        cli_path,
        "analyze",
        str(project_file),
        "--output-format",
        "json",
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(project_dir),
        )
        stdout_bytes, _ = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout_seconds,
        )
        raw_output = stdout_bytes.decode("utf-8", errors="replace")
    except FileNotFoundError:
        return AnalysisResult(
            success=True,
            analyzer_available=False,
            raw_output="UiPath CLI executable not found.",
        )
    except asyncio.TimeoutError:
        logger.warning("UiPath analysis timed out after %ds.", timeout_seconds)
        return AnalysisResult(
            success=False,
            raw_output=f"Analysis timed out after {timeout_seconds}s.",
            findings=[
                AnalysisFinding(
                    rule_id="TIMEOUT",
                    severity="error",
                    message=f"UiPath analysis exceeded {timeout_seconds}s timeout.",
                )
            ],
            error_count=1,
        )
    except OSError as exc:
        return AnalysisResult(
            success=True,
            analyzer_available=False,
            raw_output=f"Failed to run UiPath CLI: {exc}",
        )

    findings = _parse_analysis_output(raw_output)

    error_count = sum(1 for f in findings if f.severity == "error")
    warning_count = sum(1 for f in findings if f.severity == "warning")
    info_count = sum(1 for f in findings if f.severity in ("info", "verbose"))

    logger.info(
        "UiPath analysis complete: %d error(s), %d warning(s), %d info.",
        error_count,
        warning_count,
        info_count,
    )

    return AnalysisResult(
        success=proc.returncode == 0 or error_count == 0,
        findings=findings,
        error_count=error_count,
        warning_count=warning_count,
        info_count=info_count,
        raw_output=raw_output,
        analyzer_available=True,
    )
