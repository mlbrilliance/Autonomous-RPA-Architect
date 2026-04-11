"""Deployment pipeline: package, provision, and deploy to UiPath Orchestrator."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from rpa_architect.lifecycle.state import DeploymentRecord

logger = logging.getLogger(__name__)


async def deploy_project(
    project_dir: str,
    folder: str = "Default",
    ir_snapshot: dict[str, Any] | None = None,
) -> DeploymentRecord:
    """Package, provision, and deploy a UiPath project to Orchestrator.

    Args:
        project_dir: Path to the generated UiPath project directory.
        folder: Target Orchestrator folder.
        ir_snapshot: ProcessIR snapshot for traceability.

    Returns:
        DeploymentRecord with release and process keys.
    """
    project_path = Path(project_dir)
    project_json = project_path / "project.json"

    if not project_json.exists():
        raise FileNotFoundError(f"No project.json found in {project_dir}")

    project_data = json.loads(project_json.read_text(encoding="utf-8"))
    process_name = project_data.get("name", project_path.name)
    version = project_data.get("projectVersion", "1.0.0")

    # Step 1: Package the project
    package_id = await _package_project(project_path)

    # Step 2: Provision Orchestrator resources (queues, assets)
    await _provision_resources(project_path, folder)

    # Step 3: Create release in Orchestrator
    release_key, process_key = await _create_release(
        package_id=package_id,
        process_name=process_name,
        folder=folder,
    )

    return DeploymentRecord(
        process_key=process_key,
        release_key=release_key,
        package_id=package_id,
        folder=folder,
        ir_snapshot=ir_snapshot or {},
        version=version,
    )


async def _package_project(project_path: Path) -> str:
    """Package the project using the UiPath CLI or assembler."""
    try:
        from rpa_architect.platform.agent_deployer import deploy_as_agent

        result = await deploy_as_agent(project_path)
        if result.success:
            logger.info("Package created: %s", result.package_id)
            return result.package_id
        raise RuntimeError(f"Packaging failed: {'; '.join(result.errors)}")
    except ImportError:
        logger.warning("Agent deployer not available, using project name as package ID")
        return project_path.name


async def _provision_resources(project_path: Path, folder: str) -> None:
    """Provision Orchestrator resources (queues, assets, credentials)."""
    try:
        from rpa_architect.assembler.orchestrator_provisioner import provision_orchestrator

        await provision_orchestrator(project_path, folder=folder)
        logger.info("Orchestrator resources provisioned in folder %s", folder)
    except Exception as exc:
        logger.warning("Resource provisioning skipped: %s", exc)


async def _create_release(
    package_id: str,
    process_name: str,
    folder: str,
) -> tuple[str, str]:
    """Create or update a release (process) in Orchestrator.

    Returns:
        Tuple of (release_key, process_key).
    """
    from rpa_architect.config import load_config

    cfg = load_config()

    from rpa_architect.platform.sdk_client import UiPathClient

    cid = cfg.uipath.client_id
    csec = cfg.uipath.client_secret
    if not cid or not csec:
        raise RuntimeError(
            "UiPath OAuth credentials required for deployment. "
            "Set UIPATH_CLIENT_ID and UIPATH_CLIENT_SECRET."
        )

    client = UiPathClient(
        url=cfg.uipath.url,
        tenant_id=cfg.uipath.tenant_id,
        client_id=cid.get_secret_value(),
        client_secret=csec.get_secret_value(),
        folder=folder,
    )

    try:
        result = await client.create_release(
            package_id=package_id,
            process_name=process_name,
        )
        release_key = result.get("Key", "")
        process_key = result.get("ProcessKey", release_key)
        logger.info("Release created: %s (process: %s)", release_key, process_key)
        return release_key, process_key
    finally:
        await client.close()
