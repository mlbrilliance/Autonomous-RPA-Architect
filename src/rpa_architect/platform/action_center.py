"""UiPath Action Center integration for human-in-the-loop tasks.

Uses the Orchestrator REST API (OData) to create and poll Action Center
tasks, replacing the previous dependency on the phantom ``uipath-langchain``
package.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("rpa_architect.platform.action_center")


class TaskResult(BaseModel):
    """Result of creating an Action Center task."""

    task_id: str = ""
    title: str = ""
    status: str = "Created"
    created_at: float = Field(default_factory=time.time)


class TaskOutput(BaseModel):
    """Output returned when a task is completed by a human."""

    task_id: str = ""
    status: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    completed_by: str = ""


async def create_review_task(
    title: str,
    data: dict[str, Any],
    assignee: str | None = None,
    *,
    client: Any | None = None,
) -> TaskResult:
    """Create a human review task in UiPath Action Center.

    Args:
        title: Task title.
        data: Form data to include in the task.
        assignee: Optional assignee username or group.
        client: A :class:`~rpa_architect.platform.sdk_client.UiPathClient`.

    Returns:
        A :class:`TaskResult` with the created task ID.

    Raises:
        RuntimeError: If no client is provided.
    """
    if client is None:
        raise RuntimeError(
            "A UiPathClient instance is required to create Action Center tasks."
        )

    payload: dict[str, Any] = {
        "Title": title,
        "Type": "FormTask",
        "Data": data,
    }
    if assignee:
        payload["AssignedToUser"] = assignee

    result = await client._request(
        "POST",
        "Tasks/UiPath.Server.Configuration.OData.CreateFormTask",
        json=payload,
    )
    task_id = str(result.get("Id", ""))
    logger.info("Created Action Center task %s: %s", task_id, title)
    return TaskResult(task_id=task_id, title=title, status="Created")


async def wait_for_task(
    task_id: str,
    timeout: float = 3600.0,
    poll_interval: float = 10.0,
    *,
    client: Any | None = None,
) -> TaskOutput:
    """Wait for an Action Center task to be completed.

    Polls the task status until it is completed, failed, or the timeout
    expires.

    Args:
        task_id: The Action Center task ID to watch.
        timeout: Maximum seconds to wait.
        poll_interval: Seconds between status checks.
        client: A :class:`~rpa_architect.platform.sdk_client.UiPathClient`.

    Returns:
        A :class:`TaskOutput` with the task result.

    Raises:
        TimeoutError: If the task is not completed within *timeout*.
        RuntimeError: If no client is provided.
    """
    if client is None:
        raise RuntimeError(
            "A UiPathClient instance is required to poll Action Center tasks."
        )

    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        result = await client._request("GET", f"Tasks({task_id})")
        status = str(result.get("Status", ""))

        if status.lower() in ("completed", "approved", "rejected"):
            output_data = result.get("Data", {})
            if not isinstance(output_data, dict):
                output_data = {"result": str(output_data)}
            logger.info("Task %s completed with status: %s", task_id, status)
            return TaskOutput(
                task_id=task_id,
                status=status,
                data=output_data,
                completed_by=str(result.get("CompletedByUser", "")),
            )

        if status.lower() in ("failed", "cancelled"):
            logger.warning("Task %s ended with status: %s", task_id, status)
            return TaskOutput(task_id=task_id, status=status)

        await asyncio.sleep(poll_interval)

    raise TimeoutError(f"Task {task_id} did not complete within {timeout}s")
