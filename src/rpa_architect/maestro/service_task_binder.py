"""Bind Maestro plan tasks to concrete service implementations."""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field

from rpa_architect.ir.schema import ProcessIR
from rpa_architect.maestro.maestro_planner import MaestroPlan

logger = logging.getLogger("rpa_architect.maestro.binder")

BindingType = Literal["rpa_workflow", "ai_agent", "api_workflow", "queue_operation"]


class FieldMapping(BaseModel):
    """Maps a source field to a target field."""

    source: str
    target: str


class TaskBinding(BaseModel):
    """Binds a BPMN task to a concrete implementation."""

    task_id: str = Field(description="BPMN task ID from the plan.")
    binding_type: BindingType = Field(description="Type of backend implementation.")
    target_name: str = Field(description="Target process/workflow/API name.")
    input_mappings: list[FieldMapping] = Field(default_factory=list)
    output_mappings: list[FieldMapping] = Field(default_factory=list)


def bind_service_tasks(plan: MaestroPlan, ir: ProcessIR) -> list[TaskBinding]:
    """Create :class:`TaskBinding` instances for every task in the plan.

    Binding logic:

    * Tasks with ``binding_type=api_workflow`` in metadata -> ``api_workflow``
    * Tasks referencing steps with ``api_call`` type -> ``api_workflow``
    * Tasks associated with a queue credential -> ``queue_operation``
    * Everything else defaults to ``rpa_workflow``

    Input/output mappings are derived from the transaction data contracts.

    Args:
        plan: The :class:`MaestroPlan` produced by the planner.
        ir: The process intermediate representation.

    Returns:
        A list of :class:`TaskBinding`, one per BPMN task.
    """
    # Build lookup structures.
    step_map: dict[str, Any] = {}
    for txn in ir.transactions:
        for step in txn.steps:
            step_map[step.id] = step

    queue_names = {c.name for c in ir.credentials if c.type == "queue"}

    bindings: list[TaskBinding] = []

    for task_def in plan.bpmn_tasks:
        # Determine binding type.
        meta_binding = task_def.metadata.get("binding_type", "rpa_workflow")

        # Check if any referenced step is an API call.
        is_api = any(
            step_map.get(sid) and step_map[sid].type == "api_call"
            for sid in task_def.step_refs
        )
        if is_api:
            meta_binding = "api_workflow"

        # Check queue association.
        is_queue = any(
            step_map.get(sid) and step_map[sid].system_ref in queue_names
            for sid in task_def.step_refs
        )
        if is_queue:
            meta_binding = "queue_operation"

        # Build input/output mappings from transaction contracts.
        input_mappings: list[FieldMapping] = []
        output_mappings: list[FieldMapping] = []
        for txn in ir.transactions:
            txn_step_ids = {s.id for s in txn.steps}
            if txn_step_ids & set(task_def.step_refs):
                if txn.input_contract:
                    input_mappings.extend(
                        FieldMapping(source=f.name, target=f.name)
                        for f in txn.input_contract.fields
                    )
                if txn.output_contract:
                    output_mappings.extend(
                        FieldMapping(source=f.name, target=f.name)
                        for f in txn.output_contract.fields
                    )

        target_name = _derive_target_name(task_def.name, meta_binding)

        bindings.append(
            TaskBinding(
                task_id=task_def.task_id,
                binding_type=meta_binding,  # type: ignore[arg-type]
                target_name=target_name,
                input_mappings=input_mappings,
                output_mappings=output_mappings,
            )
        )

    logger.info("Bound %d service tasks", len(bindings))
    return bindings


def _derive_target_name(task_name: str, binding_type: str) -> str:
    """Generate a target process/workflow name from the task name."""
    safe = task_name.replace(" ", "_").replace("-", "_")
    safe = "".join(c for c in safe if c.isalnum() or c == "_")
    prefix_map = {
        "rpa_workflow": "RPA",
        "ai_agent": "Agent",
        "api_workflow": "API",
        "queue_operation": "Queue",
    }
    prefix = prefix_map.get(binding_type, "Task")
    return f"{prefix}_{safe}"
