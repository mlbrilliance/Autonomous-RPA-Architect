"""Selector harvesting via UiPath Design Robot."""

from __future__ import annotations

import json
import logging
from typing import Any

from rpa_architect.platform.sdk_client import UiPathClient

logger = logging.getLogger("rpa_architect.platform.design_robot")

_HARVESTER_PROCESS = "SelectorHarvester"


async def harvest_selectors(
    app_url: str,
    elements: list[str],
    sdk_client: UiPathClient,
) -> dict[str, str]:
    """Invoke the SelectorHarvester bot to discover UI selectors.

    Sends a list of element descriptions to the harvester bot running in
    UiPath and parses the returned selector strings.

    Args:
        app_url: URL or identifier of the target application.
        elements: Human-readable element descriptions to harvest selectors for.
        sdk_client: An initialised :class:`UiPathClient`.

    Returns:
        A mapping of element description to UiPath selector string.
        Elements that could not be resolved are omitted.
    """
    input_args: dict[str, Any] = {
        "AppUrl": app_url,
        "Elements": json.dumps(elements),
    }

    try:
        job_id = await sdk_client.invoke_process(
            process_key=_HARVESTER_PROCESS,
            input_arguments=input_args,
        )
        logger.info("SelectorHarvester started: job %s", job_id)
    except Exception as exc:
        logger.error("Failed to invoke SelectorHarvester: %s", exc)
        return {}

    # Poll until the job completes.
    import asyncio

    max_polls = 60
    poll_interval = 5.0

    for _ in range(max_polls):
        status = await sdk_client.get_job_status(job_id)
        if status.state.lower() in ("successful", "completed"):
            break
        if status.state.lower() in ("faulted", "stopped"):
            logger.error("SelectorHarvester job %s ended: %s", job_id, status.state)
            return {}
        await asyncio.sleep(poll_interval)
    else:
        logger.error("SelectorHarvester job %s timed out", job_id)
        return {}

    # Parse output from the job info field.
    selectors: dict[str, str] = {}
    try:
        output = json.loads(status.info) if status.info else {}
        raw_selectors = output.get("Selectors", {})
        if isinstance(raw_selectors, dict):
            selectors = {k: str(v) for k, v in raw_selectors.items()}
        elif isinstance(raw_selectors, str):
            selectors = json.loads(raw_selectors)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("Could not parse SelectorHarvester output: %s", exc)

    logger.info("Harvested %d selectors for %s", len(selectors), app_url)
    return selectors
