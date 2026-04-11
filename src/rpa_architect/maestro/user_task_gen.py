"""Generate user task definitions for human-in-the-loop steps."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from rpa_architect.ir.schema import Step

logger = logging.getLogger("rpa_architect.maestro.user_task_gen")

_APPROVAL_KEYWORDS = {"approve", "approval", "review", "sign", "confirm", "authorize", "reject"}
_DEFAULT_ESCALATION = "PT24H"  # ISO 8601 duration — 24 hours


class FormField(BaseModel):
    """A single field in a user task form."""

    field_id: str
    label: str
    field_type: str = "string"  # string, boolean, number, date, enum
    required: bool = True
    default_value: str | None = None
    options: list[str] = Field(default_factory=list)


class UserTaskDef(BaseModel):
    """Definition for a user task requiring human interaction."""

    task_id: str = Field(description="Unique task identifier.")
    name: str = Field(description="Display name for the task.")
    app_name: str = Field(description="Application context for the task.")
    form_fields: list[FormField] = Field(default_factory=list)
    assignee_expression: str = Field(
        default="",
        description="Expression resolving to the task assignee.",
    )
    escalation_timeout: str = Field(
        default=_DEFAULT_ESCALATION,
        description="ISO 8601 duration before escalation.",
    )


def _is_human_step(step: Step) -> bool:
    """Determine whether a step requires human review or approval."""
    if step.type == "decision":
        return True
    text = (step.description or "").lower()
    return any(kw in text for kw in _APPROVAL_KEYWORDS)


def _build_form_fields(step: Step) -> list[FormField]:
    """Derive form fields from a step's actions and parameters."""
    fields: list[FormField] = []

    # If the step has input parameters, expose them as read-only fields.
    for key, value in step.parameters.items():
        fields.append(
            FormField(
                field_id=f"param_{key}",
                label=key.replace("_", " ").title(),
                field_type="string",
                required=False,
                default_value=str(value) if value is not None else None,
            )
        )

    # For decision steps, add an approval boolean and comment field.
    description = (step.description or "").lower()
    if step.type == "decision" or any(kw in description for kw in _APPROVAL_KEYWORDS):
        fields.append(
            FormField(
                field_id="approved",
                label="Approved",
                field_type="boolean",
                required=True,
            )
        )
        fields.append(
            FormField(
                field_id="comments",
                label="Comments",
                field_type="string",
                required=False,
            )
        )

    return fields


def _derive_assignee(step: Step) -> str:
    """Extract or generate an assignee expression from the step."""
    params = step.parameters
    if "assignee" in params:
        return str(params["assignee"])
    if "route_to" in params:
        return str(params["route_to"])
    # Default to a role-based expression.
    return "${initiator}"


def _derive_app_name(step: Step) -> str:
    """Derive the application name from system_ref or description."""
    if step.system_ref:
        return step.system_ref
    return "ActionCenter"


def generate_user_tasks(steps: list[Step]) -> list[UserTaskDef]:
    """Identify steps requiring human review and generate task definitions.

    Args:
        steps: Flat list of IR steps to scan.

    Returns:
        A list of :class:`UserTaskDef` for each human-interaction step.
    """
    user_tasks: list[UserTaskDef] = []
    counter = 0

    for step in steps:
        if not _is_human_step(step):
            continue

        counter += 1
        task_id = f"UserTask_{counter}"
        name = step.description or f"Review Step {step.id}"

        user_tasks.append(
            UserTaskDef(
                task_id=task_id,
                name=name,
                app_name=_derive_app_name(step),
                form_fields=_build_form_fields(step),
                assignee_expression=_derive_assignee(step),
                escalation_timeout=_DEFAULT_ESCALATION,
            )
        )

    logger.info("Generated %d user task definitions", len(user_tasks))
    return user_tasks
