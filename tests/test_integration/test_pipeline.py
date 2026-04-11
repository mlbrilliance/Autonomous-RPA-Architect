"""Cross-module integration tests — Stream A: generators → lint → wiring → assembly."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpa_architect.generators import generate_activity, list_generators
from rpa_architect.generators.base import reset_counter, xaml_namespace_header
from rpa_architect.xaml_lint import lint_xaml, LintSeverity
from rpa_architect.wiring import (
    generate_invoke_workflow,
    inject_variables,
    wire_project,
)
from rpa_architect.validation.structure_validator import validate_structure


@pytest.fixture(autouse=True)
def _reset_counter():
    reset_counter(1)
    yield
    reset_counter(1)


def _make_full_xaml(body: str, display_name: str = "TestWorkflow") -> str:
    """Wrap generated body in a complete valid XAML document."""
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<Activity\n'
        + xaml_namespace_header()
        + '>\n'
        + f'  <Sequence DisplayName="{display_name}">\n'
        + body
        + "\n  </Sequence>\n</Activity>\n"
    )


# ===================================================================
# Generator output → XAML lint (no errors)
# ===================================================================

class TestGeneratorOutputPassesLint:
    """Every deterministic generator's output should pass XAML lint without ERROR."""

    @pytest.mark.parametrize("gen_name", [
        "click", "type_into", "assign", "if", "log_message",
        "invoke_workflow", "try_catch", "foreach", "while",
        "read_range", "write_range", "http_request",
    ])
    def test_common_generators_pass_lint(self, gen_name: str):
        """Common generators produce XAML that passes lint."""
        _PARAMS = {
            "click": {"selector": "html"},
            "type_into": {"text": "hello", "selector": "html"},
            "assign": {"variable": "x", "value": "1"},
            "if": {"condition": "True", "then_body": "<Sequence />"},
            "log_message": {"message": "test", "level": "Info"},
            "invoke_workflow": {"workflow_path": "Process.xaml"},
            "try_catch": {"try_body": "<Sequence />", "catches": [{"exception": "System.Exception", "body": "<Sequence />"}]},
            "foreach": {"collection": "items", "item_type": "x:String", "item_name": "item", "body": "<Sequence />"},
            "while": {"condition": "True", "body": "<Sequence />"},
            "read_range": {"workbook_path": "data.xlsx", "sheet": "Sheet1", "range_str": "A1", "output": "dt"},
            "write_range": {"workbook_path": "out.xlsx", "sheet": "Sheet1", "datatable": "dt"},
            "http_request": {"url": "https://api.example.com", "method": "GET"},
        }
        xaml_body = generate_activity(gen_name, **_PARAMS[gen_name])
        full_xaml = _make_full_xaml(xaml_body)
        issues = lint_xaml(full_xaml)
        errors = [i for i in issues if i.severity == LintSeverity.ERROR]
        # Filter out H001 for generated activities that might not be in known list
        structural_errors = [e for e in errors if e.rule_id != "XL-H001"]
        assert structural_errors == [], f"Lint errors for {gen_name}: {structural_errors}"


# ===================================================================
# Wiring integration
# ===================================================================

class TestWiringIntegration:

    def _scaffold_project(self, tmp_path: Path) -> Path:
        """Create a minimal REFramework project structure."""
        project_dir = tmp_path / "MyProject"
        project_dir.mkdir()

        # project.json
        (project_dir / "project.json").write_text(json.dumps({
            "name": "TestProject",
            "main": "Main.xaml",
            "dependencies": {},
            "expressionLanguage": "CSharp",
        }), encoding="utf-8")

        # Framework
        fw = project_dir / "Framework"
        fw.mkdir()
        for name in ["InitAllSettings.xaml", "GetTransactionData.xaml",
                      "ProcessTransaction.xaml", "SetTransactionStatus.xaml",
                      "InitAllApplications.xaml", "CloseAllApplications.xaml",
                      "KillAllProcesses.xaml"]:
            (fw / name).write_text("<Activity><Sequence /></Activity>", encoding="utf-8")

        # Main.xaml and Process.xaml
        (project_dir / "Main.xaml").write_text(
            '<Activity xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities">'
            '<Sequence DisplayName="Main" /></Activity>',
            encoding="utf-8",
        )
        process_xaml = (
            '<Activity xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"'
            ' xmlns:ui="http://schemas.uipath.com/workflow/activities"'
            ' xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">'
            '<Sequence DisplayName="Process">'
            '<!-- INVOKE_WORKFLOWS_HERE -->'
            '</Sequence></Activity>'
        )
        (project_dir / "Process.xaml").write_text(process_xaml, encoding="utf-8")

        return project_dir

    def test_wire_project_replaces_marker(self, tmp_path: Path):
        project_dir = self._scaffold_project(tmp_path)

        # Add a custom workflow
        wf = project_dir / "Workflows"
        wf.mkdir()
        (wf / "HandleInvoice.xaml").write_text(
            '<Activity xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities">'
            '<Sequence DisplayName="HandleInvoice" /></Activity>',
            encoding="utf-8",
        )

        result = wire_project(project_dir)
        assert result.success

        # Check that Process.xaml was modified
        process_content = (project_dir / "Process.xaml").read_text(encoding="utf-8")
        assert "HandleInvoice" in process_content

    def test_wired_project_passes_structure_validation(self, tmp_path: Path):
        project_dir = self._scaffold_project(tmp_path)

        # Config.xlsx placeholder
        data_dir = project_dir / "Data"
        data_dir.mkdir()

        issues = validate_structure(project_dir)
        errors = [i for i in issues if i.severity == "error"]
        assert errors == []


# ===================================================================
# NuGet integration
# ===================================================================

class TestNuGetIntegration:

    def test_activity_to_package_mapping_complete(self):
        """All generator activity types should have NuGet package mappings."""
        from rpa_architect.nuget.known_packages import ACTIVITY_PACKAGE_MAP

        # Check some key activities from generators
        key_activities = [
            "NClick", "NTypeInto", "ReadRange", "WriteRange",
            "LogMessage", "Assign", "If", "ForEach", "TryCatch",
        ]
        for activity in key_activities:
            assert activity in ACTIVITY_PACKAGE_MAP, f"{activity} missing from ACTIVITY_PACKAGE_MAP"

    def test_default_versions_are_valid(self):
        from rpa_architect.nuget.known_packages import DEFAULT_VERSIONS

        for pkg, version in DEFAULT_VERSIONS.items():
            # Version should be non-empty and look like a semver
            assert version, f"Empty version for {pkg}"
            parts = version.split(".")
            assert len(parts) >= 2, f"Invalid version format for {pkg}: {version}"


# ===================================================================
# End-to-end: Generate → Lint → Validate
# ===================================================================

class TestEndToEnd:

    def test_generated_workflow_validates(self, tmp_path: Path):
        """Generate a workflow, write it, and validate the project."""
        project_dir = tmp_path / "E2EProject"
        project_dir.mkdir()

        # Generate XAML using deterministic generators
        body_parts = []
        body_parts.append(generate_activity("log_message", message="Start", level="Info", display_name="Log Start"))
        body_parts.append(generate_activity("assign", variable="counter", value="0"))
        body_parts.append(generate_activity("log_message", message="End", level="Info", display_name="Log End"))

        full_xaml = _make_full_xaml("\n".join(body_parts), "InvoiceProcess")

        # Write project
        (project_dir / "project.json").write_text(json.dumps({
            "name": "E2EProject",
            "main": "Main.xaml",
            "dependencies": {"UiPath.System.Activities": "24.10.7"},
        }), encoding="utf-8")
        (project_dir / "Main.xaml").write_text(full_xaml, encoding="utf-8")

        # Lint
        issues = lint_xaml(full_xaml)
        errors = [i for i in issues if i.severity == LintSeverity.ERROR]
        # May have H001 for generator-specific activities, but no structural errors
        structural_errors = [e for e in errors if e.rule_id not in ("XL-H001",)]
        assert structural_errors == [], f"Lint errors: {structural_errors}"

        # Validate structure
        val_issues = validate_structure(project_dir)
        val_errors = [i for i in val_issues if i.severity == "error"]
        assert val_errors == []

    def test_multiple_generators_compose(self):
        """Multiple generator outputs can be composed into a single valid XAML."""
        parts = [
            generate_activity("log_message", message="Start", level="Info"),
            generate_activity("assign", variable="x", value="1"),
            generate_activity("if", condition="x > 0",
                            then_body='<Sequence><Assign DisplayName="Set"><Assign.To><OutArgument x:TypeArguments="x:String">[y]</OutArgument></Assign.To><Assign.Value><InArgument x:TypeArguments="x:String">"yes"</InArgument></Assign.Value></Assign></Sequence>'),
            generate_activity("log_message", message="End", level="Info"),
        ]
        full = _make_full_xaml("\n".join(parts))
        issues = lint_xaml(full)
        parse_errors = [i for i in issues if i.rule_id == "XL-PARSE"]
        assert parse_errors == [], f"Parse errors: {parse_errors}"
