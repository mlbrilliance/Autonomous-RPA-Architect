"""Generate rich UiPath Python SDK entry points with Orchestrator integration.

Produces a ``main.py`` that optionally uses ``sdk.assets.get()``,
``sdk.queues.get_item()``, and structured logging.
"""

from __future__ import annotations

import textwrap


def generate_agent_entry_point(
    process_name: str,
    queue_name: str | None = None,
    assets: list[str] | None = None,
) -> str:
    """Generate a Python ``main.py`` that uses UiPath SDK for Orchestrator integration.

    Parameters
    ----------
    process_name:
        Human-readable process name.
    queue_name:
        Optional Orchestrator queue name.  When provided the generated code
        fetches a queue item before executing logic.
    assets:
        Optional list of Orchestrator asset names to retrieve at start-up.

    Returns
    -------
    str
        Full ``main.py`` file content.
    """

    imports = [
        '"""Entry point for {proc} UiPath agent."""',
        "import logging",
        "",
        "from uipath import UiPath",
    ]

    body_lines: list[str] = []

    # SDK initialisation
    body_lines.append("sdk = UiPath()")
    body_lines.append('logger = logging.getLogger(__name__)')
    body_lines.append("")
    body_lines.append("")

    # Function definition
    body_lines.append("def main(input_data: dict | None = None) -> dict:")
    body_lines.append('    """Main agent entry point with Orchestrator integration."""')
    body_lines.append("    input_data = input_data or {}")
    body_lines.append(f'    logger.info("Starting process: {process_name}")')
    body_lines.append("")

    # Asset retrieval
    if assets:
        body_lines.append("    # Retrieve Orchestrator assets")
        body_lines.append("    assets = {}")
        for asset_name in assets:
            body_lines.append(
                f'    assets["{asset_name}"] = sdk.assets.get("{asset_name}")'
            )
        body_lines.append("")

    # Queue integration
    if queue_name:
        body_lines.append("    # Fetch queue item from Orchestrator")
        body_lines.append(
            f'    queue_item = sdk.queues.get_item("{queue_name}")'
        )
        body_lines.append("    if queue_item:")
        body_lines.append(
            '        logger.info("Processing queue item: %s", queue_item)'
        )
        body_lines.append("        try:")
        body_lines.append("            # TODO: Implement queue item processing")
        body_lines.append(
            '            sdk.queues.set_item_status(queue_item, "Successful")'
        )
        body_lines.append("        except Exception as exc:")
        body_lines.append(
            '            logger.exception("Failed to process queue item")'
        )
        body_lines.append(
            '            sdk.queues.set_item_status(queue_item, "Failed")'
        )
        body_lines.append("            raise")
        body_lines.append("")

    # Return
    body_lines.append("    # TODO: Implement process logic")
    body_lines.append(
        f'    return {{"status": "success", "process": "{process_name}"}}'
    )

    header = "\n".join(imports).format(proc=process_name)
    body = "\n".join(body_lines)

    return f"{header}\n\n\n{body}\n"
