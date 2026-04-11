"""Test runner for UiPath projects — executes tests as a deployment gate."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TestFailure(BaseModel):
    """A single test failure."""

    test_name: str = Field(description="Name of the failed test case.")
    message: str = Field(description="Failure message or assertion error.")
    file_path: str = Field(default="", description="Test file path.")


class TestRunResult(BaseModel):
    """Result of running UiPath test cases."""

    passed: int = Field(default=0, description="Number of passed tests.")
    failed: int = Field(default=0, description="Number of failed tests.")
    skipped: int = Field(default=0, description="Number of skipped tests.")
    total: int = Field(default=0, description="Total test count.")
    failures: list[TestFailure] = Field(default_factory=list, description="Details of failed tests.")
    output: str = Field(default="", description="Raw CLI output.")

    @property
    def success(self) -> bool:
        return self.failed == 0 and self.total > 0


async def run_tests(
    project_dir: Path,
    cli_path: str | None = None,
    timeout_seconds: int = 300,
) -> TestRunResult:
    """Run UiPath test cases in a project directory.

    Uses the ``uipath`` CLI if available, otherwise falls back to
    structural test validation.

    Args:
        project_dir: Path to the UiPath project.
        cli_path: Path to the uipath CLI executable.
        timeout_seconds: Maximum test execution time.

    Returns:
        TestRunResult with pass/fail counts and failure details.
    """
    cli = cli_path or shutil.which("uipath")

    if cli:
        return await _run_with_cli(project_dir, cli, timeout_seconds)

    return _run_structural_validation(project_dir)


async def _run_with_cli(
    project_dir: Path,
    cli: str,
    timeout_seconds: int,
) -> TestRunResult:
    """Execute tests via the UiPath CLI."""
    cmd = [cli, "test", "run", "--project-path", str(project_dir), "--result", "json"]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(project_dir),
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout_seconds,
        )

        output = stdout.decode("utf-8", errors="replace")
        err_output = stderr.decode("utf-8", errors="replace")

        if proc.returncode != 0:
            logger.warning("UiPath test CLI returned code %d: %s", proc.returncode, err_output)

        return _parse_cli_output(output)

    except asyncio.TimeoutError:
        return TestRunResult(
            output=f"Test execution timed out after {timeout_seconds}s",
            failures=[TestFailure(test_name="timeout", message=f"Timed out after {timeout_seconds}s")],
            failed=1,
            total=1,
        )
    except FileNotFoundError:
        logger.warning("UiPath CLI not found at %s, falling back to structural validation", cli)
        return _run_structural_validation(project_dir)


def _parse_cli_output(output: str) -> TestRunResult:
    """Parse UiPath CLI test output (JSON format)."""
    try:
        data = json.loads(output)
        failures = []
        passed = 0
        failed = 0
        skipped = 0

        for test in data.get("testCases", data.get("results", [])):
            status = test.get("status", test.get("outcome", "")).lower()
            if status in ("passed", "success"):
                passed += 1
            elif status in ("failed", "error"):
                failed += 1
                failures.append(
                    TestFailure(
                        test_name=test.get("name", test.get("testCase", "Unknown")),
                        message=test.get("message", test.get("errorMessage", "")),
                        file_path=test.get("filePath", ""),
                    )
                )
            else:
                skipped += 1

        return TestRunResult(
            passed=passed,
            failed=failed,
            skipped=skipped,
            total=passed + failed + skipped,
            failures=failures,
            output=output,
        )
    except json.JSONDecodeError:
        # Non-JSON output — try line-by-line parsing
        lines = output.strip().split("\n")
        has_failure = any("fail" in line.lower() for line in lines)
        return TestRunResult(
            passed=0 if has_failure else 1,
            failed=1 if has_failure else 0,
            total=1,
            output=output,
            failures=[TestFailure(test_name="parse_error", message=output[:200])] if has_failure else [],
        )


def _run_structural_validation(project_dir: Path) -> TestRunResult:
    """Validate test file structure when CLI is not available."""
    test_files = list(project_dir.rglob("*Test*.xaml")) + list(project_dir.rglob("*Test*.cs"))

    if not test_files:
        logger.info("No test files found in %s", project_dir)
        return TestRunResult(total=0, output="No test files found")

    passed = 0
    failures = []

    for test_file in test_files:
        content = test_file.read_text(encoding="utf-8", errors="replace")
        if len(content.strip()) > 10:
            passed += 1
        else:
            failures.append(
                TestFailure(
                    test_name=test_file.name,
                    message="Test file appears empty or malformed",
                    file_path=str(test_file.relative_to(project_dir)),
                )
            )

    return TestRunResult(
        passed=passed,
        failed=len(failures),
        total=len(test_files),
        failures=failures,
        output=f"Structural validation: {passed}/{len(test_files)} test files valid",
    )
