"""LangGraph multi-agent orchestrator for UiPath code generation."""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class GeneratedFile(BaseModel):
    """A single generated file in the UiPath project."""

    path: str
    """Relative path within the project directory."""
    content: str
    """Full file content."""
    file_type: str
    """File extension type: cs, xaml, json, xlsx, bpmn."""
    generation_task_id: str
    """ID of the GenerationTask that produced this file."""


class GenerationState(BaseModel):
    """Shared state flowing through the generation graph."""

    ir: dict[str, Any] = Field(default_factory=dict)
    """Intermediate Representation of the parsed PDD."""
    plan: list[dict[str, Any]] = Field(default_factory=list)
    """Ordered list of GenerationTask dicts produced by the planner."""
    generated_files: dict[str, GeneratedFile] = Field(default_factory=dict)
    """Map of relative path -> GeneratedFile."""
    validation_results: dict[str, Any] = Field(default_factory=dict)
    """Results from compilation and analysis validators."""
    iteration_count: int = 0
    """Current fix-recompile iteration."""
    errors: list[str] = Field(default_factory=list)
    """Accumulated error messages across iterations."""
    rag_context: str = ""
    """Assembled RAG context for the current generation pass."""


def _should_fix_or_assemble(state: GenerationState) -> str:
    """Conditional edge: route to 'fix' if there are errors and iterations remain."""
    has_errors = bool(state.errors) or not state.validation_results.get("success", True)
    within_budget = state.iteration_count < 3

    if has_errors and within_budget:
        logger.info(
            "Validation failed (iteration %d/3) — routing to fix node.",
            state.iteration_count,
        )
        return "fix"

    if has_errors:
        logger.warning(
            "Validation still failing after %d iterations — assembling best result.",
            state.iteration_count,
        )
    return "assemble"


def _assemble(state: GenerationState) -> GenerationState:
    """Terminal node: finalise the generated project."""
    logger.info(
        "Assembly complete — %d files generated, %d errors remaining.",
        len(state.generated_files),
        len(state.errors),
    )
    return state


def create_graph() -> CompiledStateGraph:
    """Build and compile the multi-agent code-generation graph.

    Node functions are imported lazily so this module can be loaded without
    pulling in heavy LLM / RAG dependencies at import time.

    Returns:
        A compiled LangGraph StateGraph ready for invocation.
    """
    from rpa_architect.codegen.coder_agent import generate
    from rpa_architect.codegen.planner_agent import plan
    from rpa_architect.codegen.reviewer_agent import review
    from rpa_architect.validation.feedback_loop import fix

    graph = StateGraph(GenerationState)

    # Register nodes
    graph.add_node("plan", plan)
    graph.add_node("generate", generate)
    graph.add_node("review", review)
    graph.add_node("validate", _validate_node)
    graph.add_node("fix", fix)
    graph.add_node("assemble", _assemble)

    # Linear edges
    graph.add_edge("plan", "generate")
    graph.add_edge("generate", "review")
    graph.add_edge("review", "validate")

    # Conditional edge after validation
    graph.add_conditional_edges(
        "validate",
        _should_fix_or_assemble,
        {"fix": "fix", "assemble": "assemble"},
    )

    # Fix loops back to generate
    graph.add_edge("fix", "generate")

    # Assemble is terminal
    graph.add_edge("assemble", END)

    # Entry point
    graph.set_entry_point("plan")

    return graph.compile()


async def _validate_node(state: GenerationState) -> GenerationState:
    """Validation node that runs compilation + structure checks."""
    import tempfile
    from pathlib import Path

    from rpa_architect.validation.roslyn_validator import validate_compilation
    from rpa_architect.validation.structure_validator import validate_structure

    # Write generated files to a temp directory for validation
    with tempfile.TemporaryDirectory(prefix="rpa_validate_") as tmpdir:
        project_dir = Path(tmpdir)
        for rel_path, gen_file in state.generated_files.items():
            file_path = project_dir / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(gen_file.content, encoding="utf-8")

        # Run validators
        compilation = await validate_compilation(project_dir)
        structure_issues = validate_structure(project_dir)

        # Run XAML hallucination linter on all generated .xaml files
        from rpa_architect.xaml_lint import lint_project

        xaml_lint_result = lint_project(project_dir)

        errors: list[str] = []
        if not compilation.success:
            errors.extend(
                f"{e.file}({e.line},{e.column}): {e.severity} {e.code}: {e.message}"
                for e in compilation.errors
            )
        errors.extend(issue.message for issue in structure_issues)

        # Add XAML lint errors (ERROR severity blocks assembly, others are warnings)
        xaml_lint_errors = [
            r for r in xaml_lint_result if any(i.severity.value == "error" for i in r.issues)
        ]
        for result in xaml_lint_result:
            for issue in result.issues:
                prefix = f"[XAML-LINT {issue.rule_id}] "
                if issue.severity.value == "error":
                    errors.append(f"{prefix}{result.file_path}: {issue.message}")
                else:
                    logger.warning("%s%s: %s", prefix, result.file_path, issue.message)

        state.validation_results = {
            "success": (
                compilation.success
                and len(structure_issues) == 0
                and len(xaml_lint_errors) == 0
            ),
            "compilation": compilation.model_dump(),
            "structure_issues": [i.model_dump() for i in structure_issues],
            "xaml_lint": [r.model_dump() for r in xaml_lint_result],
        }
        state.errors = errors
        state.iteration_count += 1

    return state
