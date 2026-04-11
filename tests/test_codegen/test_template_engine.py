"""Tests for the Jinja2 template engine."""

from __future__ import annotations

import pytest
import jinja2

from rpa_architect.codegen.template_engine import (
    TemplateEngine,
    camel_case,
    pascal_case,
)


class TestTemplateEngineInit:
    """Test TemplateEngine initialisation."""

    def test_template_engine_init(self) -> None:
        engine = TemplateEngine()
        assert engine is not None
        assert len(engine.available_templates) > 0

    def test_template_engine_with_dir(self, tmp_path) -> None:
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        (templates_dir / "custom.j2").write_text("Hello {{ name }}!")

        engine = TemplateEngine(templates_dir=templates_dir)
        assert "custom.j2" in engine.available_templates

    def test_template_engine_with_nonexistent_dir(self) -> None:
        """Non-existent directory is handled gracefully; built-ins still work."""
        engine = TemplateEngine(templates_dir="/nonexistent/path")
        assert len(engine.available_templates) > 0


class TestRenderProjectJson:
    """Test rendering the project.json template."""

    def test_render_project_json(self) -> None:
        engine = TemplateEngine()
        result = engine.render("project.json.j2", {})
        assert '"name": "GeneratedRPAProject"' in result
        assert '"schemaVersion": "4.0"' in result
        assert '"expressionLanguage": "CSharp"' in result


class TestRenderCodedWorkflow:
    """Test rendering C# coded workflow templates."""

    def test_render_coded_workflow(self) -> None:
        engine = TemplateEngine()
        context = {
            "workflow_name": "process_invoice",
            "description": "Process an invoice from queue to ERP.",
            "services": ["UiPath.UIAutomationNext.API"],
            "steps": [
                {"name": "Open Portal", "description": "Navigate to invoice portal."},
                {"name": "Extract Data", "description": "Get invoice fields."},
            ],
        }
        result = engine.render("workflow_generic.cs.j2", context)
        assert "ProcessInvoice" in result  # pascal_case applied
        assert "Process an invoice" in result
        assert "Open Portal" in result
        assert "namespace CodedWorkflows" in result

    def test_render_ui_automation_workflow(self) -> None:
        engine = TemplateEngine()
        context = {
            "workflow_name": "click_login_button",
            "services": [],
            "steps": [
                {
                    "name": "Click Login",
                    "action": "click",
                    "target": "Login Button",
                    "selector": "<webctrl tag='button' id='login' />",
                },
            ],
        }
        result = engine.render("workflow_ui_automation.cs.j2", context)
        assert "ClickLoginButton" in result
        assert "TakeScreenshot" in result


class TestPascalCaseFilter:
    """Test the pascal_case Jinja2 filter."""

    @pytest.mark.parametrize(
        "input_val, expected",
        [
            ("get_transaction_data", "GetTransactionData"),
            ("my workflow name", "MyWorkflowName"),
            ("already-pascal", "AlreadyPascal"),
            ("single", "Single"),
            ("", ""),
        ],
    )
    def test_pascal_case_filter(self, input_val: str, expected: str) -> None:
        assert pascal_case(input_val) == expected


class TestCamelCaseFilter:
    """Test the camel_case Jinja2 filter."""

    @pytest.mark.parametrize(
        "input_val, expected",
        [
            ("GetTransactionData", "getTransactionData"),
            ("my_field_name", "myFieldName"),
            ("single", "single"),
            ("", ""),
        ],
    )
    def test_camel_case_filter(self, input_val: str, expected: str) -> None:
        assert camel_case(input_val) == expected


class TestTemplateNotFound:
    """Test error on missing template."""

    def test_template_not_found(self) -> None:
        engine = TemplateEngine()
        with pytest.raises(jinja2.TemplateNotFound):
            engine.render("nonexistent_template.j2", {})
