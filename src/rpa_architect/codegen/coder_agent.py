"""Code generation agent — produces C#/XAML/JSON files from generation tasks."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from rpa_architect.codegen.planner_agent import GenerationTask, TaskType
from rpa_architect.codegen.template_engine import TemplateEngine

logger = logging.getLogger(__name__)


class GeneratedFile(BaseModel):
    """A single generated output file."""

    path: str
    """Relative path within the UiPath project."""
    content: str
    """Full file content."""
    file_type: str
    """Extension: cs, xaml, json, xlsx, bpmn."""
    generation_task_id: str
    """ID of the task that produced this file."""


# ---------------------------------------------------------------------------
# Workflow-type-specific generators
# ---------------------------------------------------------------------------

_WORKFLOW_TYPE_TEMPLATES: dict[str, str] = {
    "ui_automation": "workflow_ui_automation.cs.j2",
    "browser": "workflow_ui_automation.cs.j2",
    "web": "workflow_ui_automation.cs.j2",
    "data_transform": "workflow_data_transform.cs.j2",
    "api_call": "workflow_api_call.cs.j2",
    "http": "workflow_api_call.cs.j2",
    "rest": "workflow_api_call.cs.j2",
    "queue_processing": "workflow_queue_processing.cs.j2",
    "queue": "workflow_queue_processing.cs.j2",
    "email": "workflow_generic.cs.j2",
    "excel": "workflow_generic.cs.j2",
    "database": "workflow_generic.cs.j2",
}


def _build_template_context(task: GenerationTask, rag_context: str) -> dict[str, Any]:
    """Assemble the Jinja2 template context for a generation task."""
    ir = task.ir_subset
    return {
        "workflow_name": task.workflow_name,
        "task_type": task.task_type.value,
        "services": task.uipath_services,
        "steps": ir.get("steps", []),
        "inputs": ir.get("inputs", []),
        "outputs": ir.get("outputs", []),
        "description": ir.get("description", ""),
        "exceptions": ir.get("exceptions", []),
        "business_rule": ir.get("business_rule", ""),
        "fields": ir.get("fields", []),
        "target_workflow": ir.get("target_workflow", ""),
        "selectors": ir.get("selectors", {}),
        "config": ir.get("config", {}),
        "rag_context": rag_context,
    }


def _generate_xaml_activities(steps: list[dict[str, Any]]) -> str:
    """Generate deterministic XAML for common activity steps.

    Uses the deterministic generators module to produce structurally
    correct XAML fragments, avoiding LLM hallucination for known
    activity patterns.
    """
    from rpa_architect.generators import generate_activity, get_generator

    xaml_parts: list[str] = []
    for step in steps:
        step_type = step.get("type", "").lower()
        action = step.get("action", "").lower()
        activity_name = step_type or action

        # Map IR step types to generator names
        _STEP_TO_GENERATOR = {
            "click": "click",
            "type_into": "type_into",
            "get_text": "get_text",
            "select_item": "select_item",
            "check": "check",
            "hover": "hover",
            "assign": "assign",
            "if": "if",
            "foreach": "foreach",
            "while": "while",
            "try_catch": "try_catch",
            "log": "log_message",
            "log_message": "log_message",
            "invoke_workflow": "invoke_workflow",
            "http_request": "http_request",
            "read_range": "read_range",
            "write_range": "write_range",
        }

        gen_name = _STEP_TO_GENERATOR.get(activity_name)
        if gen_name and get_generator(gen_name):
            try:
                # Extract relevant params from the step dict
                params = {k: v for k, v in step.items() if k not in ("type", "action", "id", "name")}
                if "display_name" not in params and "name" in step:
                    params["display_name"] = step["name"]
                xaml = generate_activity(gen_name, **params)
                xaml_parts.append(xaml)
            except Exception:
                logger.debug("Deterministic gen failed for %s, will use template.", gen_name)

    return "\n".join(xaml_parts)


def _generate_workflow(
    task: GenerationTask,
    engine: TemplateEngine,
    rag_context: str,
) -> list[GeneratedFile]:
    """Generate a coded-workflow .cs file.

    Also generates companion XAML activities using deterministic
    generators for known step types, reducing hallucination.
    """
    wf_type = task.ir_subset.get("type", "generic").lower()
    template_name = _WORKFLOW_TYPE_TEMPLATES.get(wf_type, "workflow_generic.cs.j2")
    ctx = _build_template_context(task, rag_context)

    content = engine.render(template_name, ctx)
    files = [
        GeneratedFile(
            path=f"CodedWorkflows/{task.workflow_name}.cs",
            content=content,
            file_type="cs",
            generation_task_id=task.task_id,
        )
    ]

    # Generate deterministic XAML for steps that have known activity mappings
    steps = task.ir_subset.get("steps", [])
    if steps:
        xaml_content = _generate_xaml_activities(steps)
        if xaml_content.strip():
            from rpa_architect.generators.base import xaml_namespace_header

            full_xaml = (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                + xaml_namespace_header()
                + f'  <Sequence DisplayName="{task.workflow_name}">\n'
                + xaml_content
                + "\n  </Sequence>\n</Activity>\n"
            )
            files.append(
                GeneratedFile(
                    path=f"Workflows/{task.workflow_name}.xaml",
                    content=full_xaml,
                    file_type="xaml",
                    generation_task_id=task.task_id,
                )
            )

    return files


def _generate_dto(
    task: GenerationTask,
    engine: TemplateEngine,
    rag_context: str,
) -> list[GeneratedFile]:
    """Generate a DTO / data model class."""
    ctx = _build_template_context(task, rag_context)
    content = engine.render("dto.cs.j2", ctx)
    return [
        GeneratedFile(
            path=f"Models/{task.workflow_name}.cs",
            content=content,
            file_type="cs",
            generation_task_id=task.task_id,
        )
    ]


def _generate_config_wrapper(
    task: GenerationTask,
    engine: TemplateEngine,
    rag_context: str,
) -> list[GeneratedFile]:
    """Generate the Config wrapper class and Config.xlsx placeholder."""
    ctx = _build_template_context(task, rag_context)
    files: list[GeneratedFile] = []

    cs_content = engine.render("config_wrapper.cs.j2", ctx)
    files.append(
        GeneratedFile(
            path="CodedWorkflows/ConfigWrapper.cs",
            content=cs_content,
            file_type="cs",
            generation_task_id=task.task_id,
        )
    )

    # project.json stub
    project_json = engine.render("project.json.j2", ctx)
    files.append(
        GeneratedFile(
            path="project.json",
            content=project_json,
            file_type="json",
            generation_task_id=task.task_id,
        )
    )

    return files


def _generate_test(
    task: GenerationTask,
    engine: TemplateEngine,
    rag_context: str,
) -> list[GeneratedFile]:
    """Generate a coded test case stub."""
    ctx = _build_template_context(task, rag_context)
    content = engine.render("test.cs.j2", ctx)
    target = task.ir_subset.get("target_workflow", task.workflow_name)
    return [
        GeneratedFile(
            path=f"CodedTests/{target}Tests.cs",
            content=content,
            file_type="cs",
            generation_task_id=task.task_id,
        )
    ]


def _generate_selector(
    task: GenerationTask,
    engine: TemplateEngine,
    rag_context: str,
) -> list[GeneratedFile]:
    """Generate a selector repository JSON file."""
    ctx = _build_template_context(task, rag_context)
    content = engine.render("selectors.json.j2", ctx)
    return [
        GeneratedFile(
            path=f"Selectors/{task.workflow_name}.json",
            content=content,
            file_type="json",
            generation_task_id=task.task_id,
        )
    ]


_GENERATORS = {
    TaskType.WORKFLOW: _generate_workflow,
    TaskType.DTO: _generate_dto,
    TaskType.CONFIG_WRAPPER: _generate_config_wrapper,
    TaskType.TEST: _generate_test,
    TaskType.SELECTOR: _generate_selector,
}


async def generate(state: "GenerationState") -> "GenerationState":  # noqa: F821
    """Generate code files for every task in the plan.

    Updates ``state.generated_files`` with newly produced files.
    """

    engine = TemplateEngine()

    for task_dict in state.plan:
        task = GenerationTask(**task_dict)
        generator_fn = _GENERATORS.get(task.task_type)
        if generator_fn is None:
            logger.warning("No generator for task type %s — skipping.", task.task_type)
            continue

        try:
            files = generator_fn(task, engine, state.rag_context)
            for f in files:
                state.generated_files[f.path] = f
                logger.debug("Generated: %s", f.path)
        except Exception:
            logger.exception("Failed to generate task %s (%s).", task.task_id, task.workflow_name)
            state.errors.append(f"Generation failed for {task.workflow_name}: see logs.")

    logger.info("Generation pass complete — %d files produced.", len(state.generated_files))
    return state
