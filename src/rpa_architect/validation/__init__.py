"""Validation subsystem for generated UiPath projects."""

from rpa_architect.validation.feedback_loop import run_feedback_loop
from rpa_architect.validation.roslyn_validator import CompilationResult, validate_compilation
from rpa_architect.validation.selector_validator import validate_selector
from rpa_architect.validation.structure_validator import validate_structure
from rpa_architect.validation.workflow_analyzer import analyze

__all__ = [
    "CompilationResult",
    "analyze",
    "run_feedback_loop",
    "validate_compilation",
    "validate_selector",
    "validate_structure",
]
