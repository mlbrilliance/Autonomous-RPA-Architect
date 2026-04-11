"""Tests for feedback_loop — Stream B: FeedbackMetrics, fix prompts, simple fixes."""
from __future__ import annotations

import pytest

from rpa_architect.validation.feedback_loop import (
    FeedbackMetrics,
    _apply_simple_fixes,
    _build_fix_prompt,
)


# ===================================================================
# FeedbackMetrics
# ===================================================================

class TestFeedbackMetrics:

    def test_initial_state(self):
        m = FeedbackMetrics()
        assert m.iterations == []
        assert m.is_improving is True
        assert m.best_iteration == 0
        assert "No iterations" in m.summary()

    def test_record_single_iteration(self):
        m = FeedbackMetrics()
        m.record(1, error_count=5, warning_count=2)
        assert len(m.iterations) == 1
        assert m.iterations[0] == {"iteration": 1, "errors": 5, "warnings": 2}

    def test_is_improving_with_decreasing_errors(self):
        m = FeedbackMetrics()
        m.record(1, 10, 0)
        m.record(2, 5, 0)
        assert m.is_improving is True

    def test_is_not_improving_with_increasing_errors(self):
        m = FeedbackMetrics()
        m.record(1, 3, 0)
        m.record(2, 7, 0)
        assert m.is_improving is False

    def test_is_improving_with_equal_errors(self):
        m = FeedbackMetrics()
        m.record(1, 5, 0)
        m.record(2, 5, 0)
        assert m.is_improving is True

    def test_best_iteration_returns_lowest_error(self):
        m = FeedbackMetrics()
        m.record(1, 10, 0)
        m.record(2, 3, 0)
        m.record(3, 5, 0)
        assert m.best_iteration == 1  # index 1 has 3 errors

    def test_best_iteration_first_when_tied(self):
        m = FeedbackMetrics()
        m.record(1, 5, 0)
        m.record(2, 5, 0)
        assert m.best_iteration == 0  # first index with min

    def test_summary_format(self):
        m = FeedbackMetrics()
        m.record(1, 4, 1)
        m.record(2, 2, 0)
        s = m.summary()
        assert "Feedback loop summary:" in s
        assert "Iteration 1" in s
        assert "4 error(s)" in s
        assert "Iteration 2" in s
        assert "2 error(s)" in s

    def test_single_iteration_always_improving(self):
        m = FeedbackMetrics()
        m.record(1, 100, 0)
        assert m.is_improving is True


# ===================================================================
# _build_fix_prompt
# ===================================================================

class TestBuildFixPrompt:

    def test_cs_errors_produce_csharp_prompt(self):
        errors = ["Process.cs(10,5): error CS0246: The type 'DataTable' could not be found"]
        content = "class Process { DataTable dt; }"
        prompt = _build_fix_prompt(errors, content, "Process.cs")
        assert "C# compilation errors" in prompt
        assert "```csharp" in prompt
        assert "Process.cs" in prompt
        assert "CS0246" in prompt

    def test_xaml_errors_produce_xaml_prompt(self):
        errors = ["[XAML-LINT XL-H001] Unknown activity 'ReadExcel' in Main.xaml"]
        content = '<Activity><ReadExcel /></Activity>'
        prompt = _build_fix_prompt(errors, content, "Main.xaml")
        assert "XAML lint errors" in prompt
        assert "```xml" in prompt
        assert "XL-H001" in prompt

    def test_mixed_errors_on_xaml_file_uses_xaml_prompt(self):
        errors = [
            "[XAML-LINT XL-H001] Unknown activity",
            "some other error",
        ]
        content = "<Activity />"
        prompt = _build_fix_prompt(errors, content, "Workflow.xaml")
        assert "XAML lint errors" in prompt

    def test_mixed_errors_on_cs_file_uses_cs_prompt(self):
        errors = [
            "[XAML-LINT XL-H001] Unknown activity",
            "Process.cs(5,1): error CS0103: name does not exist",
        ]
        content = "class X {}"
        prompt = _build_fix_prompt(errors, content, "Process.cs")
        assert "C# compilation errors" in prompt

    def test_truncates_to_20_errors(self):
        errors = [f"error line {i}" for i in range(30)]
        prompt = _build_fix_prompt(errors, "content", "file.cs")
        # Count how many "error line" entries appear
        count = prompt.count("error line")
        assert count <= 20

    def test_includes_file_content(self):
        content = "using System;\nclass MyWorkflow { }"
        prompt = _build_fix_prompt(["some error"], content, "My.cs")
        assert "using System;" in prompt
        assert "class MyWorkflow" in prompt


# ===================================================================
# _apply_simple_fixes
# ===================================================================

class TestApplySimpleFixes:

    def test_adds_system_data_for_datatable_error(self):
        content = "class X { DataTable dt; }"
        errors = ["Process.cs(1,10): error CS0246: The type 'DataTable' could not be found"]
        fixed, remaining = _apply_simple_fixes(content, errors)
        assert "using System.Data;" in fixed
        assert len(remaining) == 0

    def test_adds_collections_generic_for_list_error(self):
        content = "class X { List<string> items; }"
        errors = ["error CS0246: The type 'List<' could not be found"]
        fixed, remaining = _apply_simple_fixes(content, errors)
        assert "using System.Collections.Generic;" in fixed
        assert len(remaining) == 0

    def test_adds_threading_tasks_for_task_error(self):
        content = "class X { async Task Run() {} }"
        errors = ["error CS0246: The type 'Task' could not be found"]
        fixed, remaining = _apply_simple_fixes(content, errors)
        assert "using System.Threading.Tasks;" in fixed
        assert len(remaining) == 0

    def test_does_not_duplicate_using(self):
        content = "using System.Data;\nclass X { DataTable dt; }"
        errors = ["error CS0246: The type 'DataTable' could not be found"]
        fixed, remaining = _apply_simple_fixes(content, errors)
        assert fixed.count("using System.Data;") == 1

    def test_passes_through_unfixable_errors(self):
        content = "class X { }"
        errors = [
            "error CS0161: not all code paths return a value",
            "error CS1002: ; expected",
        ]
        fixed, remaining = _apply_simple_fixes(content, errors)
        assert fixed == content  # No changes
        assert len(remaining) == 2

    def test_mixed_fixable_and_unfixable(self):
        content = "class X { DataTable dt; }"
        errors = [
            "error CS0246: The type 'DataTable' could not be found",
            "error CS0161: not all code paths return a value",
        ]
        fixed, remaining = _apply_simple_fixes(content, errors)
        assert "using System.Data;" in fixed
        assert len(remaining) == 1
        assert "CS0161" in remaining[0]

    def test_empty_errors_returns_unchanged(self):
        content = "class X { }"
        fixed, remaining = _apply_simple_fixes(content, [])
        assert fixed == content
        assert remaining == []
