"""Tests for the framework wiring engine."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from rpa_architect.wiring import (
    WiringResult,
    generate_invoke_workflow,
    inject_variables,
    wire_project,
)
from rpa_architect.wiring.invoke_linker import (
    generate_argument_binding,
    generate_invoke_chain,
)
from rpa_architect.wiring.variable_injector import (
    generate_variable_xaml,
    scan_variable_references,
)


# ---------------------------------------------------------------------------
# Shared XAML templates
# ---------------------------------------------------------------------------

PROCESS_XAML = """\
<?xml version="1.0" encoding="utf-8"?>
<Activity
  xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
  xmlns:ui="http://schemas.uipath.com/workflow/activities"
  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
  xmlns:sap2010="http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation">
  <Sequence DisplayName="Process Transaction">
    <ui:LogMessage Level="Info" Message="Processing..." DisplayName="Log" />
  </Sequence>
</Activity>
"""

WORKFLOW_XAML = """\
<?xml version="1.0" encoding="utf-8"?>
<Activity
  xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
  xmlns:ui="http://schemas.uipath.com/workflow/activities"
  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
  xmlns:scg="clr-namespace:System.Collections.Generic;assembly=mscorlib"
  xmlns:sap2010="http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation">
  <x:Members>
    <x:Property Name="in_Config" Type="InArgument(scg:Dictionary(x:String, x:Object))" />
  </x:Members>
  <Sequence DisplayName="Process Invoice">
    <Assign DisplayName="Set Result">
      <Assign.To>
        <OutArgument x:TypeArguments="x:String">[result]</OutArgument>
      </Assign.To>
      <Assign.Value>
        <InArgument x:TypeArguments="x:String">[Config("AppURL").ToString]</InArgument>
      </Assign.Value>
    </Assign>
  </Sequence>
</Activity>
"""

XAML_WITH_VARIABLES = """\
<?xml version="1.0" encoding="utf-8"?>
<Activity
  xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
  xmlns:ui="http://schemas.uipath.com/workflow/activities"
  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName="Main">
    <Sequence.Variables>
      <Variable x:TypeArguments="x:String" Name="existingVar" />
    </Sequence.Variables>
    <ui:LogMessage Level="Info" Message="[existingVar]" DisplayName="Log" />
  </Sequence>
</Activity>
"""


# ===================================================================
# generate_invoke_workflow()
# ===================================================================

class TestGenerateInvokeWorkflow:

    def test_produces_valid_xml(self):
        xml_str = generate_invoke_workflow("Workflows/Process.xaml")
        # Wrap for parsing
        wrapped = (
            '<Root xmlns:ui="http://schemas.uipath.com/workflow/activities">'
            f'{xml_str}</Root>'
        )
        root = ET.fromstring(wrapped)
        assert root is not None

    def test_contains_workflow_filename(self):
        xml_str = generate_invoke_workflow("Workflows/Process.xaml")
        assert "WorkflowFileName" in xml_str
        # UiPath normalizes to backslashes
        assert "Workflows\\Process.xaml" in xml_str

    def test_display_name_defaults_to_stem(self):
        xml_str = generate_invoke_workflow("Workflows/ProcessInvoice.xaml")
        assert 'DisplayName="ProcessInvoice"' in xml_str

    def test_custom_display_name(self):
        xml_str = generate_invoke_workflow(
            "Workflows/Sub.xaml", display_name="My Sub Workflow"
        )
        assert 'DisplayName="My Sub Workflow"' in xml_str

    def test_without_arguments_is_self_closing(self):
        xml_str = generate_invoke_workflow("Workflows/Simple.xaml")
        assert xml_str.strip().endswith("/>")

    def test_with_arguments_includes_bindings(self):
        xml_str = generate_invoke_workflow(
            "Workflows/Process.xaml",
            arguments={
                "Config": ("In", "Config"),
                "Result": ("Out", "outputVar"),
            },
        )
        assert "InvokeWorkflowFile.Arguments" in xml_str
        assert "InArgument" in xml_str
        assert "OutArgument" in xml_str

    def test_with_inout_argument(self):
        xml_str = generate_invoke_workflow(
            "Workflows/Process.xaml",
            arguments={"SharedData": ("InOut", "sharedVar")},
        )
        assert "InOutArgument" in xml_str


# ===================================================================
# generate_argument_binding()
# ===================================================================

class TestGenerateArgumentBinding:

    def test_in_argument(self):
        xml_str = generate_argument_binding("Config", "In", "Config")
        assert "<InArgument" in xml_str
        assert 'x:Key="in_Config"' in xml_str
        assert "[Config]" in xml_str

    def test_out_argument(self):
        xml_str = generate_argument_binding("Result", "Out", "resultVar")
        assert "<OutArgument" in xml_str
        assert 'x:Key="out_Result"' in xml_str

    def test_inout_argument(self):
        xml_str = generate_argument_binding("Shared", "InOut", "sharedVar")
        assert "<InOutArgument" in xml_str
        assert 'x:Key="io_Shared"' in xml_str

    def test_value_not_double_bracketed(self):
        """If value already has brackets, should not add more."""
        xml_str = generate_argument_binding("X", "In", "[alreadyBracketed]")
        assert "[[" not in xml_str  # No double brackets

    def test_unknown_direction_defaults_to_in(self):
        xml_str = generate_argument_binding("X", "Unknown", "val")
        assert "<InArgument" in xml_str


# ===================================================================
# generate_invoke_chain()
# ===================================================================

class TestGenerateInvokeChain:

    def test_wraps_in_sequence(self):
        xml_str = generate_invoke_chain([
            {"path": "Workflows/A.xaml"},
            {"path": "Workflows/B.xaml"},
        ])
        assert "<Sequence" in xml_str
        assert "</Sequence>" in xml_str

    def test_contains_all_workflows(self):
        xml_str = generate_invoke_chain([
            {"path": "Workflows/Step1.xaml"},
            {"path": "Workflows/Step2.xaml"},
            {"path": "Workflows/Step3.xaml"},
        ])
        assert "Step1" in xml_str
        assert "Step2" in xml_str
        assert "Step3" in xml_str

    def test_shared_variables_passed(self):
        xml_str = generate_invoke_chain(
            [{"path": "Workflows/Process.xaml"}],
            shared_variables={"Config": "Config"},
        )
        assert "Config" in xml_str
        assert "InArgument" in xml_str

    def test_workflow_specific_args_override_shared(self):
        xml_str = generate_invoke_chain(
            [
                {
                    "path": "Workflows/Process.xaml",
                    "arguments": {"Config": ("In", "CustomConfig")},
                },
            ],
            shared_variables={"Config": "Config"},
        )
        # Workflow-specific arg should take precedence
        assert "CustomConfig" in xml_str


# ===================================================================
# inject_variables()
# ===================================================================

class TestInjectVariables:

    def test_injects_new_variable(self, tmp_path: Path):
        xaml_file = tmp_path / "test.xaml"
        xaml_file.write_text(XAML_WITH_VARIABLES, encoding="utf-8")

        injected = inject_variables(
            xaml_file,
            [{"name": "newVar", "type": "x:Int32"}],
        )
        assert "newVar" in injected

        content = xaml_file.read_text(encoding="utf-8")
        assert "newVar" in content
        assert "x:Int32" in content

    def test_skips_already_declared_variable(self, tmp_path: Path):
        xaml_file = tmp_path / "test.xaml"
        xaml_file.write_text(XAML_WITH_VARIABLES, encoding="utf-8")

        injected = inject_variables(
            xaml_file,
            [{"name": "existingVar", "type": "x:String"}],
        )
        # existingVar is already declared, should be skipped
        assert "existingVar" not in injected

    def test_idempotent_injection(self, tmp_path: Path):
        xaml_file = tmp_path / "test.xaml"
        xaml_file.write_text(XAML_WITH_VARIABLES, encoding="utf-8")

        variables = [{"name": "newVar", "type": "x:String"}]
        inject_variables(xaml_file, variables)
        content_after_first = xaml_file.read_text(encoding="utf-8")

        # Inject again -- should not add a second declaration
        injected2 = inject_variables(xaml_file, variables)
        assert injected2 == []  # Nothing new to inject

        content_after_second = xaml_file.read_text(encoding="utf-8")
        assert content_after_first == content_after_second

    def test_nonexistent_file_returns_empty(self, tmp_path: Path):
        fake = tmp_path / "no_such_file.xaml"
        result = inject_variables(fake, [{"name": "x", "type": "x:String"}])
        assert result == []

    def test_empty_variables_list(self, tmp_path: Path):
        xaml_file = tmp_path / "test.xaml"
        xaml_file.write_text(XAML_WITH_VARIABLES, encoding="utf-8")
        result = inject_variables(xaml_file, [])
        assert result == []


# ===================================================================
# scan_variable_references()
# ===================================================================

class TestScanVariableReferences:

    def test_detects_bracket_references(self):
        xaml = '<Assign Value="[Config]" /><Assign Value="[TransactionItem.SpecificContent]" />'
        refs = scan_variable_references(xaml)
        assert "Config" in refs
        assert "TransactionItem" in refs

    def test_detects_dotted_references(self):
        xaml = 'Config.ContainsKey("SettingName")'
        refs = scan_variable_references(xaml)
        assert "Config" in refs

    def test_filters_out_noise(self):
        xaml = '<Sequence DisplayName="Main"><Variable Name="x" /></Sequence>'
        refs = scan_variable_references(xaml)
        # "Sequence", "Variable", etc. are noise and should be filtered
        assert "Sequence" not in refs
        assert "Variable" not in refs

    def test_empty_content(self):
        refs = scan_variable_references("")
        assert refs == set()

    def test_argument_binding_references(self):
        xaml = '<InArgument x:TypeArguments="x:String">[myData]</InArgument>'
        refs = scan_variable_references(xaml)
        assert "myData" in refs


# ===================================================================
# generate_variable_xaml()
# ===================================================================

class TestGenerateVariableXaml:

    def test_basic_variable(self):
        xml_str = generate_variable_xaml("myVar", "x:String")
        assert '<Variable' in xml_str
        assert 'Name="myVar"' in xml_str
        assert 'x:TypeArguments="x:String"' in xml_str
        assert xml_str.strip().endswith("/>")

    def test_with_default_value(self):
        xml_str = generate_variable_xaml("count", "x:Int32", default="0")
        assert 'Default="0"' in xml_str

    def test_with_annotation(self):
        xml_str = generate_variable_xaml(
            "Config", "x:Object", annotation="Configuration dictionary"
        )
        assert "AnnotationText" in xml_str
        assert "Configuration dictionary" in xml_str

    def test_special_characters_escaped(self):
        xml_str = generate_variable_xaml("var", "x:String", default='"Hello"')
        assert "&quot;" in xml_str


# ===================================================================
# wire_project()
# ===================================================================

class TestWireProject:

    def _create_project(self, tmp_path: Path) -> Path:
        """Create a minimal UiPath project structure for testing."""
        project_dir = tmp_path / "MyProject"
        project_dir.mkdir()

        # Framework directory with Process.xaml
        fw_dir = project_dir / "Framework"
        fw_dir.mkdir()
        (fw_dir / "Process.xaml").write_text(PROCESS_XAML, encoding="utf-8")

        # Workflows directory with a custom workflow
        wf_dir = project_dir / "Workflows"
        wf_dir.mkdir()
        (wf_dir / "ProcessInvoice.xaml").write_text(WORKFLOW_XAML, encoding="utf-8")

        return project_dir

    def test_wire_project_basic(self, tmp_path: Path):
        project_dir = self._create_project(tmp_path)
        result = wire_project(project_dir)

        assert isinstance(result, WiringResult)
        assert result.success is True
        assert len(result.actions) > 0

    def test_wire_project_inserts_invocation(self, tmp_path: Path):
        project_dir = self._create_project(tmp_path)
        result = wire_project(project_dir)

        # Should have an invoke_inserted action
        invoke_actions = [
            a for a in result.actions if a.action_type == "invoke_inserted"
        ]
        assert len(invoke_actions) >= 1

        # Process.xaml should now contain the invocation
        process_content = (project_dir / "Framework" / "Process.xaml").read_text(
            encoding="utf-8"
        )
        assert "InvokeWorkflowFile" in process_content

    def test_wire_project_nonexistent_directory(self, tmp_path: Path):
        fake_dir = tmp_path / "DoesNotExist"
        result = wire_project(fake_dir)

        assert result.success is False
        assert len(result.errors) > 0

    def test_wire_project_no_workflows(self, tmp_path: Path):
        project_dir = tmp_path / "EmptyProject"
        project_dir.mkdir()

        result = wire_project(project_dir)
        assert result.success is True
        assert len(result.warnings) > 0
        assert any("No custom workflows" in w for w in result.warnings)

    def test_wire_project_no_process_xaml(self, tmp_path: Path):
        """Project with workflows but no Framework/Process.xaml."""
        project_dir = tmp_path / "NoFramework"
        project_dir.mkdir()
        wf_dir = project_dir / "Workflows"
        wf_dir.mkdir()
        (wf_dir / "Sub.xaml").write_text(WORKFLOW_XAML, encoding="utf-8")

        result = wire_project(project_dir)
        # Should warn about missing Process.xaml
        assert any("Process.xaml" in w for w in result.warnings)

    def test_wire_project_idempotent(self, tmp_path: Path):
        """Running wire_project twice should not duplicate invocations."""
        project_dir = self._create_project(tmp_path)

        result1 = wire_project(project_dir)
        result2 = wire_project(project_dir)

        # Second run should skip already-invoked workflows
        invoke_actions_2 = [
            a for a in result2.actions if a.action_type == "invoke_inserted"
        ]
        assert len(invoke_actions_2) == 0


# ===================================================================
# WiringResult model
# ===================================================================

class TestWiringResultModel:

    def test_default_values(self):
        result = WiringResult()
        assert result.success is True
        assert result.actions == []
        assert result.warnings == []
        assert result.errors == []

    def test_with_errors_sets_success_false(self):
        result = WiringResult(
            success=False,
            errors=["Something went wrong"],
        )
        assert result.success is False
        assert len(result.errors) == 1

    def test_actions_list(self):
        from rpa_architect.wiring.wiring_engine import WiringAction

        result = WiringResult(
            actions=[
                WiringAction(
                    action_type="invoke_inserted",
                    target_file="Process.xaml",
                    detail="Inserted invocation",
                ),
                WiringAction(
                    action_type="variable_injected",
                    target_file="Sub.xaml",
                    detail="Injected Config variable",
                ),
            ]
        )
        assert len(result.actions) == 2
        assert result.actions[0].action_type == "invoke_inserted"
        assert result.actions[1].action_type == "variable_injected"
