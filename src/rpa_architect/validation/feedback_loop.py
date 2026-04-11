"""LLMLOOP feedback — iterative compile-fix cycle for generated code."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rpa_architect.codegen.orchestrator import GenerationState

logger = logging.getLogger(__name__)


class FeedbackMetrics:
    """Tracks improvement across feedback iterations."""

    def __init__(self) -> None:
        self.iterations: list[dict[str, int]] = []

    def record(self, iteration: int, error_count: int, warning_count: int) -> None:
        self.iterations.append({
            "iteration": iteration,
            "errors": error_count,
            "warnings": warning_count,
        })

    @property
    def is_improving(self) -> bool:
        """Check if the error count is trending down."""
        if len(self.iterations) < 2:
            return True
        return self.iterations[-1]["errors"] <= self.iterations[-2]["errors"]

    @property
    def best_iteration(self) -> int:
        """Return the iteration index with the fewest errors."""
        if not self.iterations:
            return 0
        return min(range(len(self.iterations)), key=lambda i: self.iterations[i]["errors"])

    def summary(self) -> str:
        if not self.iterations:
            return "No iterations recorded."
        lines = ["Feedback loop summary:"]
        for entry in self.iterations:
            lines.append(
                f"  Iteration {entry['iteration']}: "
                f"{entry['errors']} error(s), {entry['warnings']} warning(s)"
            )
        return "\n".join(lines)


def _build_fix_prompt(errors: list[str], file_content: str, file_path: str) -> str:
    """Build an LLM prompt to fix compilation or XAML lint errors in a file."""
    relevant_errors = [e for e in errors if file_path in e or not any("(" in e for _ in [1])]

    # Separate XAML lint errors from C# compilation errors
    xaml_errors = [e for e in relevant_errors if "[XAML-LINT" in e]
    cs_errors = [e for e in relevant_errors if "[XAML-LINT" not in e]

    is_xaml = file_path.endswith(".xaml")

    prompt_parts = []
    if is_xaml and xaml_errors:
        prompt_parts.extend([
            "Fix the following XAML lint errors in this UiPath workflow file.",
            "These errors indicate hallucinated or invalid XAML elements.",
            "",
            f"File: {file_path}",
            "",
            "XAML Lint Errors:",
        ])
        for err in xaml_errors[:20]:
            prompt_parts.append(f"  - {err}")
        prompt_parts.extend([
            "",
            "Current file content:",
            "```xml",
            file_content,
            "```",
            "",
            "Return ONLY the corrected XAML, no explanations.",
        ])
    else:
        prompt_parts.extend([
            "Fix the following C# compilation errors in this UiPath coded workflow file.",
            "",
            f"File: {file_path}",
            "",
            "Errors:",
        ])
        for err in (cs_errors or relevant_errors)[:20]:
            prompt_parts.append(f"  - {err}")
        prompt_parts.extend([
            "",
            "Current file content:",
            "```csharp",
            file_content,
            "```",
            "",
            "Return ONLY the corrected C# code, no explanations.",
        ])

    return "\n".join(prompt_parts)


def _apply_simple_fixes(content: str, errors: list[str]) -> tuple[str, list[str]]:
    """Apply deterministic fixes for common compilation errors.

    Returns the (possibly modified) content and list of remaining unfixed errors.
    """
    fixed_content = content
    remaining_errors: list[str] = []

    for error in errors:
        error_lower = error.lower()

        # CS0246: Missing using directive
        if "cs0246" in error_lower:
            if "DataTable" in error and "using System.Data;" not in fixed_content:
                fixed_content = "using System.Data;\n" + fixed_content
                continue
            if "List<" in error and "using System.Collections.Generic;" not in fixed_content:
                fixed_content = "using System.Collections.Generic;\n" + fixed_content
                continue
            if "Task" in error and "using System.Threading.Tasks;" not in fixed_content:
                fixed_content = "using System.Threading.Tasks;\n" + fixed_content
                continue

        # CS0161: Not all code paths return a value — harder to auto-fix
        # CS1002: ; expected — usually structural, leave to LLM
        # CS0103: Name does not exist — usually a typo or missing import

        remaining_errors.append(error)

    return fixed_content, remaining_errors


async def fix(state: "GenerationState") -> "GenerationState":
    """Fix node in the generation graph.

    Attempts deterministic fixes first, then prepares error context for
    the next generate pass.
    """
    logger.info(
        "Fix node: iteration %d, %d error(s) to address.",
        state.iteration_count,
        len(state.errors),
    )

    # Group errors by file
    file_errors: dict[str, list[str]] = {}
    general_errors: list[str] = []

    for error in state.errors:
        # Try to extract file path from error format: "path/File.cs(line,col): ..."
        if "(" in error and ":" in error:
            file_part = error.split("(")[0].strip()
            if file_part:
                file_errors.setdefault(file_part, []).append(error)
                continue
        general_errors.append(error)

    # Apply deterministic fixes to each affected file
    files_modified = 0
    remaining_all_errors: list[str] = list(general_errors)

    for file_path, errors in file_errors.items():
        # Find the generated file
        gen_file = state.generated_files.get(file_path)
        if gen_file is None:
            # Try matching by filename only
            filename = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path
            for key, gf in state.generated_files.items():
                if key.endswith(filename):
                    gen_file = gf
                    break

        if gen_file is None:
            remaining_all_errors.extend(errors)
            continue

        fixed_content, remaining = _apply_simple_fixes(gen_file.content, errors)
        if fixed_content != gen_file.content:
            gen_file.content = fixed_content
            files_modified += 1
            logger.info("Applied deterministic fixes to %s.", gen_file.path)

        remaining_all_errors.extend(remaining)

    # Store remaining errors as context for the next generate pass
    if remaining_all_errors:
        error_context = "\n".join(
            [
                "=== Compilation Errors from Previous Iteration ===",
                f"Iteration: {state.iteration_count}",
                "",
            ]
            + remaining_all_errors
            + ["", "Fix these errors in the next generation pass."]
        )
        # Prepend error context to RAG context so the generator sees it
        state.rag_context = error_context + "\n\n" + state.rag_context

    state.errors = remaining_all_errors
    logger.info(
        "Fix pass complete: %d files modified, %d errors remaining.",
        files_modified,
        len(remaining_all_errors),
    )

    return state


async def run_feedback_loop(
    state: "GenerationState",
    max_iterations: int = 3,
) -> "GenerationState":
    """Run the full compile-fix-recompile feedback loop.

    This is a standalone entry point for running the feedback loop outside
    of the LangGraph orchestrator.

    Args:
        state: Current generation state with generated files.
        max_iterations: Maximum number of fix attempts.

    Returns:
        Updated state with the best result achieved.
    """
    from rpa_architect.codegen.coder_agent import generate
    from rpa_architect.codegen.orchestrator import _validate_node

    metrics = FeedbackMetrics()

    # Store snapshots keyed by iteration for rollback
    best_files: dict[str, any] = {}
    best_error_count = float("inf")

    for iteration in range(max_iterations):
        logger.info("Feedback loop iteration %d/%d.", iteration + 1, max_iterations)

        # Validate
        state = await _validate_node(state)

        error_count = len([e for e in state.errors if "error" in e.lower()])
        warning_count = len(state.errors) - error_count
        metrics.record(iteration + 1, error_count, warning_count)

        # Track best result
        if error_count < best_error_count:
            best_error_count = error_count
            best_files = {k: v.model_copy() for k, v in state.generated_files.items()}

        # Success — no errors
        if error_count == 0:
            logger.info("Feedback loop succeeded after %d iteration(s).", iteration + 1)
            break

        # No improvement for 2 consecutive iterations — give up early
        if not metrics.is_improving and iteration > 0:
            logger.warning("No improvement detected — stopping feedback loop early.")
            break

        # Apply fixes and regenerate
        state = await fix(state)
        state = await generate(state)

    else:
        logger.warning(
            "Feedback loop exhausted %d iterations — using best result (iteration %d).",
            max_iterations,
            metrics.best_iteration + 1,
        )
        # Restore best snapshot
        if best_files:
            state.generated_files = best_files

    logger.info(metrics.summary())
    return state
