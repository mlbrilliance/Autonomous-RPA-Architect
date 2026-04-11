"""Planning agent — decomposes IR into ordered generation tasks."""

from __future__ import annotations

import logging
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    """Types of generation tasks."""

    WORKFLOW = "workflow"
    DTO = "dto"
    CONFIG_WRAPPER = "config_wrapper"
    TEST = "test"
    SELECTOR = "selector"


class GenerationTask(BaseModel):
    """A single unit of work for the code generator."""

    task_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    task_type: TaskType
    workflow_name: str
    dependencies: list[str] = Field(default_factory=list)
    """task_ids that must be generated before this task."""
    ir_subset: dict[str, Any] = Field(default_factory=dict)
    """Slice of the IR relevant to this task."""
    rag_queries: list[str] = Field(default_factory=list)
    """Queries to run against the RAG knowledge base for context."""
    uipath_services: list[str] = Field(default_factory=list)
    """UiPath services required (e.g. ILogService, IBrowserService)."""


def _detect_uipath_services(step: dict[str, Any]) -> list[str]:
    """Infer which UiPath coded-workflow services a step needs."""
    services: set[str] = set()
    step_type = step.get("type", "").lower()
    description = step.get("description", "").lower()
    applications = step.get("applications", [])

    # Always inject logging
    services.add("Uqido.UiPath.Activities.ILogService")

    if step_type in ("ui_automation", "click", "type_into", "screen"):
        services.add("UiPath.UIAutomationNext.API.Contracts.IUiAutomationAppService")
    if step_type in ("browser", "web") or any("browser" in a.lower() for a in applications):
        services.add("UiPath.UIAutomationNext.API.Contracts.IBrowserService")
    if step_type in ("excel", "spreadsheet") or any("excel" in a.lower() for a in applications):
        services.add("UiPath.Excel.Activities.API.IExcelService")
    if step_type in ("api_call", "http", "rest"):
        services.add("UiPath.WebAPI.Activities.IHttpClientService")
    if step_type in ("queue", "orchestrator"):
        services.add("UiPath.Orchestrator.Activities.IOrchestratorService")
    if step_type in ("email", "outlook", "mail"):
        services.add("UiPath.Mail.Activities.IMailService")
    if step_type in ("database", "sql", "data"):
        services.add("UiPath.Database.Activities.IDatabaseService")

    # Heuristics from description text
    if "browser" in description or "web" in description or "chrome" in description:
        services.add("UiPath.UIAutomationNext.API.Contracts.IBrowserService")
    if "excel" in description or "spreadsheet" in description:
        services.add("UiPath.Excel.Activities.API.IExcelService")
    if "email" in description or "outlook" in description:
        services.add("UiPath.Mail.Activities.IMailService")
    if "api" in description or "http" in description or "rest" in description:
        services.add("UiPath.WebAPI.Activities.IHttpClientService")

    return sorted(services)


def _build_rag_queries(task_type: TaskType, workflow_name: str, ir_subset: dict[str, Any]) -> list[str]:
    """Generate RAG queries relevant to the task."""
    queries: list[str] = []

    if task_type == TaskType.WORKFLOW:
        queries.append(f"UiPath coded workflow example {workflow_name}")
        step_type = ir_subset.get("type", "")
        if step_type:
            queries.append(f"UiPath {step_type} activity pattern C#")
    elif task_type == TaskType.DTO:
        queries.append(f"UiPath DataTable DTO pattern {workflow_name}")
    elif task_type == TaskType.CONFIG_WRAPPER:
        queries.append("UiPath REFramework Config.xlsx access pattern coded workflow")
    elif task_type == TaskType.TEST:
        queries.append(f"UiPath coded test case pattern {workflow_name}")
    elif task_type == TaskType.SELECTOR:
        queries.append(f"UiPath selector best practices {workflow_name}")

    queries.append("UiPath CodedWorkflow base class service injection")
    return queries


def _topological_sort(tasks: list[GenerationTask]) -> list[GenerationTask]:
    """Sort tasks so dependencies come first."""
    id_to_task = {t.task_id: t for t in tasks}
    visited: set[str] = set()
    result: list[GenerationTask] = []

    def visit(task_id: str) -> None:
        if task_id in visited:
            return
        visited.add(task_id)
        task = id_to_task.get(task_id)
        if task is None:
            return
        for dep_id in task.dependencies:
            visit(dep_id)
        result.append(task)

    for t in tasks:
        visit(t.task_id)

    return result


async def plan(state: "GenerationState") -> "GenerationState":  # noqa: F821 — forward ref
    """Decompose the IR into an ordered list of GenerationTasks.

    Populates ``state.plan`` with serialized task dicts in dependency order.
    """

    ir = state.ir
    tasks: list[GenerationTask] = []
    workflow_task_ids: dict[str, str] = {}

    # --- 1. Config wrapper (always first) ---
    config_task = GenerationTask(
        task_type=TaskType.CONFIG_WRAPPER,
        workflow_name="ConfigWrapper",
        ir_subset=ir.get("config", {}),
        rag_queries=_build_rag_queries(TaskType.CONFIG_WRAPPER, "ConfigWrapper", {}),
    )
    tasks.append(config_task)

    # --- 2. DTOs for data structures ---
    data_objects = ir.get("data_objects", [])
    dto_task_ids: list[str] = []
    for obj in data_objects:
        dto_task = GenerationTask(
            task_type=TaskType.DTO,
            workflow_name=obj.get("name", "DataObject"),
            dependencies=[config_task.task_id],
            ir_subset=obj,
            rag_queries=_build_rag_queries(TaskType.DTO, obj.get("name", ""), obj),
        )
        tasks.append(dto_task)
        dto_task_ids.append(dto_task.task_id)

    # --- 3. Workflows ---
    workflows = ir.get("workflows", [])
    for wf in workflows:
        wf_name = wf.get("name", "Workflow")
        services = _detect_uipath_services(wf)

        # Workflows depend on config + any DTOs
        deps = [config_task.task_id] + dto_task_ids

        # Detect inter-workflow dependencies
        invokes = wf.get("invokes", [])
        for invoked_name in invokes:
            if invoked_name in workflow_task_ids:
                deps.append(workflow_task_ids[invoked_name])

        wf_task = GenerationTask(
            task_type=TaskType.WORKFLOW,
            workflow_name=wf_name,
            dependencies=deps,
            ir_subset=wf,
            rag_queries=_build_rag_queries(TaskType.WORKFLOW, wf_name, wf),
            uipath_services=services,
        )
        tasks.append(wf_task)
        workflow_task_ids[wf_name] = wf_task.task_id

    # --- 4. Selectors for UI automation workflows ---
    for wf in workflows:
        wf_name = wf.get("name", "Workflow")
        wf_type = wf.get("type", "").lower()
        if wf_type in ("ui_automation", "browser", "web", "click", "type_into", "screen"):
            sel_task = GenerationTask(
                task_type=TaskType.SELECTOR,
                workflow_name=f"{wf_name}_Selectors",
                dependencies=[workflow_task_ids[wf_name]],
                ir_subset=wf.get("selectors", {}),
                rag_queries=_build_rag_queries(TaskType.SELECTOR, wf_name, wf),
            )
            tasks.append(sel_task)

    # --- 5. Test stubs ---
    for wf in workflows:
        wf_name = wf.get("name", "Workflow")
        test_task = GenerationTask(
            task_type=TaskType.TEST,
            workflow_name=f"{wf_name}_Test",
            dependencies=[workflow_task_ids[wf_name]],
            ir_subset={"target_workflow": wf_name},
            rag_queries=_build_rag_queries(TaskType.TEST, wf_name, wf),
        )
        tasks.append(test_task)

    # --- Topological sort ---
    ordered = _topological_sort(tasks)

    state.plan = [t.model_dump() for t in ordered]
    logger.info("Plan created: %d tasks in dependency order.", len(ordered))
    return state
