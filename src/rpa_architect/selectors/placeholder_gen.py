"""Placeholder selector generation for UI actions.

Generates TODO-annotated selector stubs for every UIAction in the IR,
giving developers a starting point that they can refine with UiPath Explorer.
"""

from __future__ import annotations

import re

from rpa_architect.ir.schema import ProcessIR, Step, UIAction


def _sanitize_element_name(step_id: str, action: UIAction, index: int) -> str:
    """Create a safe element name from step ID and action target."""
    raw = f"{step_id}_{action.target}"
    # Replace non-alphanumeric characters with underscores
    sanitized = re.sub(r"[^a-zA-Z0-9]", "_", raw)
    # Collapse multiple underscores and strip leading/trailing
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return f"{sanitized}_{index}"


def _collect_actions(steps: list[Step]) -> list[tuple[str, int, UIAction]]:
    """Recursively collect all UIActions from steps and substeps."""
    result: list[tuple[str, int, UIAction]] = []
    for step in steps:
        for idx, action in enumerate(step.actions):
            result.append((step.id, idx, action))
        # Recurse into substeps
        result.extend(_collect_actions(step.substeps))
    return result


def generate_placeholder_selectors(ir: ProcessIR) -> dict[str, str]:
    """Generate placeholder selectors for every UIAction in the IR.

    For each UIAction, produces a UiPath-style XML selector with TODO
    markers that a developer should fill in using UiPath Explorer or
    the vision inference pipeline.

    Args:
        ir: The ProcessIR containing transactions and steps with UIActions.

    Returns:
        Dictionary mapping element_name -> selector_xml placeholder string.
    """
    selectors: dict[str, str] = {}

    for transaction in ir.transactions:
        actions = _collect_actions(transaction.steps)

        for step_id, idx, action in actions:
            element_name = _sanitize_element_name(step_id, action, idx)

            # Use selector_hint if available, otherwise generate placeholder
            if action.selector_hint:
                selector_xml = action.selector_hint
            else:
                selector_xml = (
                    f"<html app='TODO_APP' tag='TODO_TAG' "
                    f"aaname='TODO: {action.target}' />"
                )

            selectors[element_name] = selector_xml

    return selectors
