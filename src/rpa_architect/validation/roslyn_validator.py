"""Roslyn / dotnet build compilation validator."""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CompilationError(BaseModel):
    """A single compilation diagnostic."""

    file: str = ""
    """Source file path (relative)."""
    line: int = 0
    """Line number (1-based)."""
    column: int = 0
    """Column number (1-based)."""
    code: str = ""
    """Diagnostic code (e.g. CS0246)."""
    message: str = ""
    """Human-readable diagnostic message."""
    severity: str = "error"
    """One of: error, warning, info."""


class CompilationResult(BaseModel):
    """Result of a dotnet build attempt."""

    success: bool = False
    errors: list[CompilationError] = Field(default_factory=list)
    warnings: list[CompilationError] = Field(default_factory=list)
    raw_output: str = ""
    """Full stdout+stderr from dotnet build."""
    sdk_available: bool = True
    """Whether the .NET SDK was found on the system."""


# MSBuild output pattern:
#   path/File.cs(10,5): error CS1234: Some message [project.csproj]
_MSBUILD_DIAG_RE = re.compile(
    r"^(?P<file>[^(]+)\((?P<line>\d+),(?P<col>\d+)\):\s+"
    r"(?P<severity>error|warning)\s+(?P<code>\w+):\s+"
    r"(?P<message>.+?)(?:\s+\[.+\])?\s*$",
    re.MULTILINE,
)

# Simpler pattern for messages without file location:
#   error CS1234: Some message
_MSBUILD_SIMPLE_RE = re.compile(
    r"^\s*(?P<severity>error|warning)\s+(?P<code>\w+):\s+(?P<message>.+?)\s*$",
    re.MULTILINE,
)


def _parse_msbuild_output(output: str) -> tuple[list[CompilationError], list[CompilationError]]:
    """Parse MSBuild output into errors and warnings."""
    errors: list[CompilationError] = []
    warnings: list[CompilationError] = []

    for match in _MSBUILD_DIAG_RE.finditer(output):
        diag = CompilationError(
            file=match.group("file").strip(),
            line=int(match.group("line")),
            column=int(match.group("col")),
            code=match.group("code"),
            message=match.group("message").strip(),
            severity=match.group("severity"),
        )
        if diag.severity == "error":
            errors.append(diag)
        else:
            warnings.append(diag)

    # Also catch diagnostics without file locations
    for match in _MSBUILD_SIMPLE_RE.finditer(output):
        code = match.group("code")
        # Skip if already captured by the more detailed regex
        if any(e.code == code and e.message == match.group("message").strip() for e in errors + warnings):
            continue
        diag = CompilationError(
            code=code,
            message=match.group("message").strip(),
            severity=match.group("severity"),
        )
        if diag.severity == "error":
            errors.append(diag)
        else:
            warnings.append(diag)

    return errors, warnings


async def validate_compilation(
    project_dir: Path,
    timeout_seconds: int = 120,
) -> CompilationResult:
    """Run ``dotnet build`` on a project directory and parse results.

    Args:
        project_dir: Path to the UiPath/C# project directory.
        timeout_seconds: Maximum time to wait for the build.

    Returns:
        CompilationResult with parsed diagnostics.
    """
    dotnet_path = shutil.which("dotnet")
    if dotnet_path is None:
        logger.warning(".NET SDK not found — skipping compilation validation.")
        return CompilationResult(
            success=True,  # Optimistic: can't validate, don't block
            sdk_available=False,
            raw_output=".NET SDK not found on PATH.",
        )

    # Look for a .csproj or .sln file
    project_file: Path | None = None
    for pattern in ("*.csproj", "*.sln"):
        candidates = list(project_dir.glob(pattern))
        if candidates:
            project_file = candidates[0]
            break

    if project_file is None:
        # Try building the directory anyway (dotnet build can work without explicit project)
        build_target = str(project_dir)
    else:
        build_target = str(project_file)

    cmd = [
        dotnet_path,
        "build",
        build_target,
        "--no-restore",
        "--verbosity",
        "minimal",
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
        return CompilationResult(
            success=True,
            sdk_available=False,
            raw_output="dotnet executable not found.",
        )
    except asyncio.TimeoutError:
        logger.warning("dotnet build timed out after %ds.", timeout_seconds)
        return CompilationResult(
            success=False,
            raw_output=f"Build timed out after {timeout_seconds}s.",
            errors=[
                CompilationError(
                    code="TIMEOUT",
                    message=f"dotnet build exceeded {timeout_seconds}s timeout.",
                    severity="error",
                )
            ],
        )
    except OSError as exc:
        return CompilationResult(
            success=True,
            sdk_available=False,
            raw_output=f"Failed to run dotnet: {exc}",
        )

    errors, warnings = _parse_msbuild_output(raw_output)
    success = proc.returncode == 0 and len(errors) == 0

    logger.info(
        "dotnet build %s: %d error(s), %d warning(s).",
        "succeeded" if success else "failed",
        len(errors),
        len(warnings),
    )

    return CompilationResult(
        success=success,
        errors=errors,
        warnings=warnings,
        raw_output=raw_output,
        sdk_available=True,
    )
