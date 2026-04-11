"""UiPath project packaging and publishing.

Wraps the ``uipath pack`` and ``uipath publish`` CLI commands to
produce .nupkg packages and push them to Orchestrator feeds.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class PackageResult(BaseModel):
    """Result of a UiPath pack operation."""

    success: bool = Field(description="Whether packaging succeeded.")
    nupkg_path: Path | None = Field(
        default=None,
        description="Path to the generated .nupkg file.",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Error messages from the pack process.",
    )


class PublishResult(BaseModel):
    """Result of a UiPath publish operation."""

    success: bool = Field(description="Whether publishing succeeded.")
    feed_url: str = Field(
        default="",
        description="Feed URL the package was published to.",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Error messages from the publish process.",
    )


def _find_uipath_cli() -> str | None:
    """Locate the UiPath CLI executable."""
    # Check common names
    for name in ("uipath", "uipcli", "UiPath.CLI"):
        path = shutil.which(name)
        if path:
            return path
    return None


async def package_project(
    project_dir: Path,
    *,
    output_dir: Path | None = None,
    cli_path: str | None = None,
    use_manual_fallback: bool = True,
) -> PackageResult:
    """Package a UiPath project into a .nupkg file.

    Tries ``uipath pack`` (or ``uipcli package pack``) first. If the CLI is
    not installed, or if it fails (e.g. the Linux build refuses to pack
    Windows-targeted projects), falls back to a Python-based packager that
    assembles the .nupkg directly using :mod:`zipfile`. The resulting
    archive is platform-neutral and runs fine on a Windows Unattended
    robot.

    Args:
        project_dir: Path to the UiPath project directory (containing project.json).
        output_dir: Directory to write the .nupkg file. Defaults to project_dir/output.
        cli_path: Explicit path to the UiPath CLI. Auto-detected if not provided.
        use_manual_fallback: When True (default) fall back to the manual
            Python packager on CLI failure or absence.

    Returns:
        PackageResult with success status and .nupkg path.
    """
    cli = cli_path or _find_uipath_cli()

    if cli is None:
        if use_manual_fallback:
            return _try_manual_pack(project_dir, output_dir)
        return PackageResult(
            success=False,
            errors=[
                "UiPath CLI not found. Install it with: "
                "dotnet tool install UiPath.CLI.Linux -g (or .Windows / .Macos)"
            ],
        )

    if output_dir is None:
        output_dir = project_dir / "output"

    output_dir.mkdir(parents=True, exist_ok=True)

    project_json = project_dir / "project.json"
    if not project_json.exists():
        return PackageResult(
            success=False,
            errors=[f"project.json not found in {project_dir}."],
        )

    cmd = [
        cli,
        "package", "pack",
        str(project_dir),
        "--output", str(output_dir),
    ]

    # uipcli needs DOTNET_ROOT to find the .NET 8 runtime when it was
    # installed to ~/.dotnet (standard install path for Linux dev envs).
    import os as _os

    env = _os.environ.copy()
    dotnet_root = _os.environ.get("DOTNET_ROOT") or str(Path.home() / ".dotnet")
    if Path(dotnet_root).exists():
        env["DOTNET_ROOT"] = dotnet_root
        env["PATH"] = (
            f"{dotnet_root}:{dotnet_root}/tools:" + env.get("PATH", "")
        )

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await proc.communicate()
    except FileNotFoundError:
        return PackageResult(
            success=False,
            errors=[f"Failed to execute UiPath CLI at '{cli}'."],
        )
    except OSError as exc:
        return PackageResult(
            success=False,
            errors=[f"OS error running UiPath CLI: {exc}"],
        )

    if proc.returncode != 0:
        error_output = stderr.decode("utf-8", errors="replace").strip()
        if use_manual_fallback:
            logger.warning(
                "uipcli pack failed (exit %d); falling back to manual packager. "
                "Original error: %s",
                proc.returncode,
                error_output[:500],
            )
            return _try_manual_pack(project_dir, output_dir)
        return PackageResult(
            success=False,
            errors=[f"uipath pack failed (exit {proc.returncode}): {error_output}"],
        )

    # Find the generated .nupkg
    nupkg_files = list(output_dir.glob("*.nupkg"))
    nupkg_path = nupkg_files[0] if nupkg_files else None

    if nupkg_path is None:
        if use_manual_fallback:
            return _try_manual_pack(project_dir, output_dir)
        return PackageResult(
            success=False,
            errors=["Pack completed but no .nupkg file found in output directory."],
        )

    logger.info("Packaged project to %s.", nupkg_path)

    return PackageResult(
        success=True,
        nupkg_path=nupkg_path,
    )


def _try_manual_pack(
    project_dir: Path, output_dir: Path | None
) -> PackageResult:
    """Build a .nupkg using the in-process Python packager."""
    from rpa_architect.assembler.manual_packager import pack_project_manually

    try:
        nupkg = pack_project_manually(project_dir, output_dir=output_dir)
    except Exception as exc:  # noqa: BLE001 - surface as error result
        return PackageResult(
            success=False,
            errors=[f"manual packager failed: {exc}"],
        )
    logger.info("Packaged project via manual packager: %s", nupkg)
    return PackageResult(success=True, nupkg_path=nupkg)


async def publish_project(
    nupkg_path: Path,
    feed: str,
    *,
    cli_path: str | None = None,
    api_key: str | None = None,
) -> PublishResult:
    """Publish a .nupkg package to a UiPath Orchestrator feed.

    Runs ``uipath publish`` as a subprocess.

    Args:
        nupkg_path: Path to the .nupkg file to publish.
        feed: Feed URL or name to publish to.
        cli_path: Explicit path to the UiPath CLI.
        api_key: API key for feed authentication.

    Returns:
        PublishResult with success status and feed URL.
    """
    cli = cli_path or _find_uipath_cli()

    if cli is None:
        return PublishResult(
            success=False,
            errors=[
                "UiPath CLI not found. Install it with: "
                "dotnet tool install UiPath.CLI -g"
            ],
        )

    if not nupkg_path.exists():
        return PublishResult(
            success=False,
            errors=[f".nupkg file not found: {nupkg_path}"],
        )

    cmd = [
        cli,
        "package", "deploy",
        str(nupkg_path),
        "--feed", feed,
    ]

    if api_key:
        cmd.extend(["--apiKey", api_key])

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
    except FileNotFoundError:
        return PublishResult(
            success=False,
            errors=[f"Failed to execute UiPath CLI at '{cli}'."],
        )
    except OSError as exc:
        return PublishResult(
            success=False,
            errors=[f"OS error running UiPath CLI: {exc}"],
        )

    if proc.returncode != 0:
        error_output = stderr.decode("utf-8", errors="replace").strip()
        return PublishResult(
            success=False,
            errors=[f"uipath publish failed (exit {proc.returncode}): {error_output}"],
        )

    logger.info("Published %s to feed '%s'.", nupkg_path.name, feed)

    return PublishResult(
        success=True,
        feed_url=feed,
    )
