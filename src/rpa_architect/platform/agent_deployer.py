"""Deploy generated projects as UiPath agents.

Uses the UiPath CLI to pack and publish projects. The CLI binary is
auto-detected via :func:`~rpa_architect.assembler.packager._find_uipath_cli`.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, Field

from rpa_architect.assembler.packager import (
    PackageResult,
    PublishResult,
    package_project,
    publish_project,
)

logger = logging.getLogger("rpa_architect.platform.agent_deployer")


class DeployResult(BaseModel):
    """Result of an agent deployment operation."""

    success: bool = False
    package_id: str = ""
    process_key: str = ""
    errors: list[str] = Field(default_factory=list)


async def deploy_as_agent(
    project_dir: Path,
    feed: str = "default",
    api_key: str | None = None,
) -> DeployResult:
    """Package and publish a UiPath project as an agent.

    Delegates to the packager module which handles CLI discovery,
    command construction, and error handling.

    Args:
        project_dir: Path to the generated UiPath project directory.
        feed: Orchestrator feed URL or name to publish to.
        api_key: Optional API key for feed authentication.

    Returns:
        A :class:`DeployResult` with status and identifiers.
    """
    result = DeployResult()

    # Step 1: Pack
    pack_result: PackageResult = await package_project(project_dir)
    if not pack_result.success:
        result.errors = pack_result.errors
        return result

    if pack_result.nupkg_path:
        result.package_id = pack_result.nupkg_path.stem

    # Step 2: Publish
    if pack_result.nupkg_path:
        pub_result: PublishResult = await publish_project(
            pack_result.nupkg_path,
            feed=feed,
            api_key=api_key,
        )
        if not pub_result.success:
            result.errors = pub_result.errors
            return result

    result.success = True
    logger.info(
        "Deployment succeeded: package=%s",
        result.package_id,
    )
    return result
