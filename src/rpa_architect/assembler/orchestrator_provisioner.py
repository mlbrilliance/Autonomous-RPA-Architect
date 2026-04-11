"""Orchestrator provisioning for UiPath projects.

Creates queues, verifies assets, and provisions folders in UiPath
Orchestrator based on the ProcessIR credential and resource definitions.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from rpa_architect.ir.schema import ProcessIR

logger = logging.getLogger(__name__)


class ProvisionResult(BaseModel):
    """Result of Orchestrator provisioning operations."""

    queues_created: list[str] = Field(
        default_factory=list,
        description="Names of queues that were created.",
    )
    assets_verified: list[str] = Field(
        default_factory=list,
        description="Names of assets that were verified to exist.",
    )
    folders_created: list[str] = Field(
        default_factory=list,
        description="Names of folders that were created.",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Error messages from provisioning operations.",
    )

    @property
    def success(self) -> bool:
        """Whether provisioning completed without errors."""
        return len(self.errors) == 0


@runtime_checkable
class OrchestratorSDKClient(Protocol):
    """Protocol for a UiPath Orchestrator SDK client.

    Expected methods correspond to the UiPath Python SDK or a
    compatible wrapper.
    """

    async def create_queue(self, name: str, **kwargs: Any) -> Any: ...
    async def get_asset(self, name: str, **kwargs: Any) -> Any: ...
    async def create_folder(self, name: str, **kwargs: Any) -> Any: ...
    async def get_folder(self, name: str, **kwargs: Any) -> Any: ...


async def _create_queues(
    ir: ProcessIR,
    sdk_client: Any,
    result: ProvisionResult,
) -> None:
    """Create Orchestrator queues for queue-type credentials."""
    queue_credentials = [c for c in ir.credentials if c.type == "queue"]

    for cred in queue_credentials:
        queue_name = cred.name
        try:
            await sdk_client.create_queue(
                name=queue_name,
                description=cred.description or f"Queue for {ir.process_name}",
            )
            result.queues_created.append(queue_name)
            logger.info("Created queue: %s", queue_name)
        except Exception as exc:
            error_msg = f"Failed to create queue '{queue_name}': {exc}"
            # Check if it's a "already exists" type error
            error_str = str(exc).lower()
            if "already exists" in error_str or "conflict" in error_str:
                logger.info("Queue '%s' already exists; skipping.", queue_name)
                result.queues_created.append(f"{queue_name} (existing)")
            else:
                logger.warning(error_msg)
                result.errors.append(error_msg)


async def _verify_assets(
    ir: ProcessIR,
    sdk_client: Any,
    result: ProvisionResult,
) -> None:
    """Verify that required assets exist in Orchestrator."""
    asset_credentials = [
        c for c in ir.credentials if c.type in ("credential", "asset")
    ]

    for cred in asset_credentials:
        asset_name = cred.name
        try:
            await sdk_client.get_asset(name=asset_name)
            result.assets_verified.append(asset_name)
            logger.info("Verified asset exists: %s", asset_name)
        except Exception as exc:
            error_str = str(exc).lower()
            if "not found" in error_str or "404" in error_str:
                result.errors.append(
                    f"Asset '{asset_name}' not found in Orchestrator. "
                    f"Please create it before running the process."
                )
            else:
                result.errors.append(
                    f"Failed to verify asset '{asset_name}': {exc}"
                )


async def _create_folders(
    ir: ProcessIR,
    sdk_client: Any,
    result: ProvisionResult,
) -> None:
    """Create Orchestrator folders if they don't exist."""
    # Collect unique folder paths from credentials
    folders: set[str] = set()

    for cred in ir.credentials:
        if cred.orchestrator_path:
            # Extract folder from path (format: "folder/asset_name")
            parts = cred.orchestrator_path.rsplit("/", 1)
            if len(parts) == 2:
                folders.add(parts[0])

    for folder_name in sorted(folders):
        try:
            # Check if folder exists
            await sdk_client.get_folder(name=folder_name)
            logger.info("Folder '%s' already exists.", folder_name)
        except Exception:
            # Try to create it
            try:
                await sdk_client.create_folder(name=folder_name)
                result.folders_created.append(folder_name)
                logger.info("Created folder: %s", folder_name)
            except Exception as exc:
                error_msg = f"Failed to create folder '{folder_name}': {exc}"
                logger.warning(error_msg)
                result.errors.append(error_msg)


async def provision_orchestrator(
    ir: ProcessIR,
    sdk_client: Any,
) -> ProvisionResult:
    """Provision UiPath Orchestrator resources based on the ProcessIR.

    Creates queues, verifies assets exist, and creates folders as needed.
    Operations are best-effort: failures are recorded in the result but
    do not prevent other operations from running.

    Args:
        ir: The ProcessIR containing credential and resource definitions.
        sdk_client: A UiPath Orchestrator SDK client or compatible wrapper.
            Must implement create_queue, get_asset, create_folder, and
            get_folder async methods.

    Returns:
        ProvisionResult with lists of created/verified resources and any errors.
    """
    result = ProvisionResult()

    # Create queues
    await _create_queues(ir, sdk_client, result)

    # Verify assets
    await _verify_assets(ir, sdk_client, result)

    # Create folders
    await _create_folders(ir, sdk_client, result)

    if result.success:
        logger.info(
            "Orchestrator provisioning complete: %d queues, %d assets verified, %d folders.",
            len(result.queues_created),
            len(result.assets_verified),
            len(result.folders_created),
        )
    else:
        logger.warning(
            "Orchestrator provisioning completed with %d error(s).",
            len(result.errors),
        )

    return result
