"""Tests for coder_agent — Stream C: _generate_xaml_activities and integration."""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from rpa_architect.codegen.coder_agent import (
    GeneratedFile,
    _generate_xaml_activities,
)
from rpa_architect.generators.base import reset_counter


@pytest.fixture(autouse=True)
def _reset_counter():
    reset_counter(1)
    yield
    reset_counter(1)


# ===================================================================
# _generate_xaml_activities
# ===================================================================

class TestGenerateXamlActivities:

    def test_click_step_produces_xaml(self):
        steps = [{"type": "click", "selector": "<html />", "name": "Click Button"}]
        result = _generate_xaml_activities(steps)
        assert result.strip() != ""
        assert "NClick" in result or "Click" in result

    def test_type_into_step(self):
        steps = [{"type": "type_into", "text": "hello", "selector": "<html />"}]
        result = _generate_xaml_activities(steps)
        assert "hello" in result

    def test_log_message_step(self):
        steps = [{"type": "log", "message": "Starting process", "level": "Info"}]
        result = _generate_xaml_activities(steps)
        assert "Starting process" in result

    def test_log_message_alternate_type(self):
        steps = [{"type": "log_message", "message": "Done", "level": "Info"}]
        result = _generate_xaml_activities(steps)
        assert "Done" in result

    def test_assign_step(self):
        steps = [{"type": "assign", "variable": "counter", "value": "0"}]
        result = _generate_xaml_activities(steps)
        assert "counter" in result

    def test_if_step(self):
        steps = [{"type": "if", "condition": "x > 0", "then_body": "<Sequence />"}]
        result = _generate_xaml_activities(steps)
        assert "If" in result

    def test_foreach_step(self):
        steps = [{"type": "foreach", "collection": "items", "item_type": "x:String", "item_name": "item", "body": "<Sequence />"}]
        result = _generate_xaml_activities(steps)
        assert "ForEach" in result

    def test_try_catch_step(self):
        steps = [{"type": "try_catch", "try_body": "<Sequence />", "catches": [{"exception": "System.Exception", "body": "<Sequence />"}]}]
        result = _generate_xaml_activities(steps)
        assert "TryCatch" in result

    def test_invoke_workflow_step(self):
        steps = [{"type": "invoke_workflow", "workflow_path": "Process.xaml"}]
        result = _generate_xaml_activities(steps)
        assert "Process.xaml" in result

    def test_http_request_step(self):
        steps = [{"type": "http_request", "url": "https://api.example.com", "method": "GET"}]
        result = _generate_xaml_activities(steps)
        assert "api.example.com" in result

    def test_read_range_step(self):
        steps = [{"type": "read_range", "workbook_path": "data.xlsx", "sheet": "Sheet1", "range_str": "A1", "output": "dt"}]
        result = _generate_xaml_activities(steps)
        assert "data.xlsx" in result

    def test_unknown_step_type_returns_empty(self):
        steps = [{"type": "unknown_activity_xyz", "param": "val"}]
        result = _generate_xaml_activities(steps)
        assert result.strip() == ""

    def test_empty_steps_returns_empty(self):
        result = _generate_xaml_activities([])
        assert result.strip() == ""

    def test_multiple_steps_concatenated(self):
        steps = [
            {"type": "log", "message": "Start", "level": "Info"},
            {"type": "assign", "variable": "x", "value": "1"},
            {"type": "log", "message": "End", "level": "Info"},
        ]
        result = _generate_xaml_activities(steps)
        assert "Start" in result
        assert "End" in result

    def test_step_name_used_as_display_name(self):
        steps = [{"type": "click", "name": "Click Submit", "selector": "<html />"}]
        result = _generate_xaml_activities(steps)
        assert "Click Submit" in result

    def test_graceful_on_bad_params(self):
        """Generator should not crash on unexpected param types."""
        steps = [{"type": "assign"}]  # Missing required params
        # Should not raise — falls back gracefully
        result = _generate_xaml_activities(steps)
        # May or may not produce output, but should not crash
        assert isinstance(result, str)

    def test_action_field_fallback(self):
        """Steps can use 'action' instead of 'type'."""
        steps = [{"action": "click", "selector": "<html />"}]
        result = _generate_xaml_activities(steps)
        assert "Click" in result or "NClick" in result


# ===================================================================
# GeneratedFile model
# ===================================================================

class TestGeneratedFileModel:

    def test_create_generated_file(self):
        f = GeneratedFile(
            path="CodedWorkflows/Process.cs",
            content="class X {}",
            file_type="cs",
            generation_task_id="task-1",
        )
        assert f.path == "CodedWorkflows/Process.cs"
        assert f.file_type == "cs"

    def test_generated_file_serialization(self):
        f = GeneratedFile(
            path="test.xaml",
            content="<Activity />",
            file_type="xaml",
            generation_task_id="task-2",
        )
        data = f.model_dump()
        assert data["path"] == "test.xaml"
        assert data["content"] == "<Activity />"
