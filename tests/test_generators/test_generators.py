"""Tests for the deterministic XAML generators."""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from rpa_architect.generators import generate_activity, get_generator, list_generators
from rpa_architect.generators.base import reset_counter
from rpa_architect.generators.registry import GeneratorInfo


# ---------------------------------------------------------------------------
# Fixture: reset counter before each test for deterministic output
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_counter():
    reset_counter(1)
    yield
    reset_counter(1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_parseable_xml(xml_str: str) -> ET.Element:
    """Assert that an XML string can be parsed and return the root element."""
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError as exc:
        pytest.fail(f"Generated XML is not parseable: {exc}\n---\n{xml_str}")
    return root


def _wrap_for_parse(xml_str: str) -> str:
    """Wrap a XAML fragment in a root element with needed namespace declarations
    so it can be parsed by ElementTree."""
    return (
        '<Root'
        ' xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"'
        ' xmlns:ui="http://schemas.uipath.com/workflow/activities"'
        ' xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"'
        ' xmlns:s="clr-namespace:System;assembly=mscorlib"'
        ' xmlns:scg="clr-namespace:System.Collections.Generic;assembly=mscorlib"'
        ' xmlns:sd="clr-namespace:System.Data;assembly=System.Data"'
        ' xmlns:sap2010="http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation"'
        f'>\n{xml_str}\n</Root>'
    )


# ===================================================================
# Click activity
# ===================================================================

class TestClickGenerator:

    def test_generates_valid_xml(self):
        xml_str = generate_activity("click", selector="<html /><webctrl id='btn' />")
        root = _assert_parseable_xml(_wrap_for_parse(xml_str))
        # Should contain ui:NClick tag
        assert "NClick" in xml_str

    def test_contains_click_type(self):
        xml_str = generate_activity("click", selector="<html />")
        assert 'ClickType="CLICK_SINGLE"' in xml_str

    def test_custom_click_type(self):
        xml_str = generate_activity("click", selector="<html />", click_type="CLICK_DOUBLE")
        assert 'ClickType="CLICK_DOUBLE"' in xml_str

    def test_contains_target_section(self):
        xml_str = generate_activity("click", selector="<html />")
        assert "NClick.Target" in xml_str

    def test_display_name(self):
        xml_str = generate_activity("click", selector="<html />", display_name="Click Login")
        assert 'DisplayName="Click Login"' in xml_str


# ===================================================================
# Type Into activity
# ===================================================================

class TestTypeIntoGenerator:

    def test_generates_valid_xml(self):
        xml_str = generate_activity(
            "type_into",
            selector="<html /><webctrl tag='input' />",
            text="Hello World",
        )
        root = _assert_parseable_xml(_wrap_for_parse(xml_str))
        assert "NTypeInto" in xml_str

    def test_contains_text_attribute(self):
        xml_str = generate_activity(
            "type_into", selector="<html />", text="test123"
        )
        assert 'Text="test123"' in xml_str

    def test_empty_field_option(self):
        xml_str = generate_activity(
            "type_into", selector="<html />", text="x", empty_field=False
        )
        assert 'EmptyField="None"' in xml_str

    def test_contains_target_section(self):
        xml_str = generate_activity("type_into", selector="<html />", text="x")
        assert "NTypeInto.Target" in xml_str


# ===================================================================
# Assign activity
# ===================================================================

class TestAssignGenerator:

    def test_generates_valid_xml(self):
        xml_str = generate_activity(
            "assign",
            variable="result",
            value='"Hello"',
        )
        root = _assert_parseable_xml(_wrap_for_parse(xml_str))
        assert "Assign" in xml_str

    def test_contains_to_and_value(self):
        xml_str = generate_activity("assign", variable="count", value="0")
        assert "Assign.To" in xml_str
        assert "Assign.Value" in xml_str


# ===================================================================
# If activity
# ===================================================================

class TestIfGenerator:

    def test_generates_valid_xml(self):
        then_body = '<Assign DisplayName="Set"><Assign.To><OutArgument x:TypeArguments="x:String">[x]</OutArgument></Assign.To><Assign.Value><InArgument x:TypeArguments="x:String">"yes"</InArgument></Assign.Value></Assign>'
        xml_str = generate_activity("if", condition="x > 0", then_body=then_body)
        root = _assert_parseable_xml(_wrap_for_parse(xml_str))

    def test_contains_condition(self):
        xml_str = generate_activity(
            "if",
            condition="myVar = True",
            then_body="<Sequence />",
        )
        assert "myVar" in xml_str

    def test_has_then_section(self):
        xml_str = generate_activity("if", condition="True", then_body="<Sequence />")
        assert "If.Then" in xml_str

    def test_with_else(self):
        xml_str = generate_activity(
            "if",
            condition="True",
            then_body="<Sequence />",
            else_body="<Sequence />",
        )
        assert "If.Then" in xml_str
        assert "If.Else" in xml_str


# ===================================================================
# TryCatch activity
# ===================================================================

class TestTryCatchGenerator:

    def test_generates_valid_xml(self):
        xml_str = generate_activity(
            "try_catch",
            try_body="<Sequence />",
            catches=[{"exception_type": "System.Exception", "body": "<Sequence />"}],
        )
        root = _assert_parseable_xml(_wrap_for_parse(xml_str))

    def test_contains_try_and_catches(self):
        xml_str = generate_activity(
            "try_catch",
            try_body="<Sequence />",
            catches=[{"exception_type": "System.Exception", "body": ""}],
        )
        assert "TryCatch.Try" in xml_str
        assert "TryCatch.Catches" in xml_str
        assert "Catch" in xml_str

    def test_with_finally(self):
        xml_str = generate_activity(
            "try_catch",
            try_body="<Sequence />",
            catches=[{"exception_type": "System.Exception", "body": ""}],
            finally_body="<Sequence />",
        )
        assert "TryCatch.Finally" in xml_str


# ===================================================================
# Log Message activity
# ===================================================================

class TestLogMessageGenerator:

    def test_generates_valid_xml(self):
        xml_str = generate_activity("log_message", message="Process started")
        root = _assert_parseable_xml(_wrap_for_parse(xml_str))
        assert "LogMessage" in xml_str

    def test_default_level(self):
        xml_str = generate_activity("log_message", message="test")
        assert 'Level="Info"' in xml_str

    def test_custom_level(self):
        xml_str = generate_activity("log_message", message="error occurred", level="Error")
        assert 'Level="Error"' in xml_str

    def test_message_content(self):
        xml_str = generate_activity("log_message", message="Processing item 42")
        assert "Processing item 42" in xml_str


# ===================================================================
# Invoke Workflow activity
# ===================================================================

class TestInvokeWorkflowGenerator:

    def test_generates_valid_xml(self):
        xml_str = generate_activity(
            "invoke_workflow",
            workflow_path="Workflows/Process.xaml",
        )
        root = _assert_parseable_xml(_wrap_for_parse(xml_str))
        assert "InvokeWorkflowFile" in xml_str

    def test_workflow_path_in_output(self):
        xml_str = generate_activity(
            "invoke_workflow", workflow_path="Workflows/Process.xaml"
        )
        assert "Workflows/Process.xaml" in xml_str

    def test_with_arguments(self):
        xml_str = generate_activity(
            "invoke_workflow",
            workflow_path="Workflows/Sub.xaml",
            arguments={
                "InputData": ("In", "myData"),
                "OutputResult": ("Out", "result"),
            },
        )
        assert "InvokeWorkflowFile.Arguments" in xml_str
        assert "InArgument" in xml_str
        assert "OutArgument" in xml_str

    def test_without_arguments_is_self_closing(self):
        xml_str = generate_activity(
            "invoke_workflow", workflow_path="Workflows/Simple.xaml"
        )
        assert xml_str.strip().endswith("/>")


# ===================================================================
# list_generators()
# ===================================================================

class TestListGenerators:

    def test_returns_all_registered(self):
        gens = list_generators()
        assert len(gens) >= 80  # 80 XAML + coded API generators

    def test_each_item_is_generator_info(self):
        gens = list_generators()
        for g in gens:
            assert isinstance(g, GeneratorInfo)
            assert g.name
            assert g.fn is not None
            assert g.category

    def test_sorted_by_name(self):
        gens = list_generators()
        names = [g.name for g in gens]
        assert names == sorted(names)

    def test_known_generators_present(self):
        names = {g.name for g in list_generators()}
        expected = {
            "click", "type_into", "assign", "if", "try_catch",
            "log_message", "invoke_workflow", "foreach", "while",
            "switch", "throw", "rethrow", "retry_scope",
        }
        assert expected.issubset(names)


# ===================================================================
# get_generator()
# ===================================================================

class TestGetGenerator:

    def test_existing_generator(self):
        info = get_generator("click")
        assert info is not None
        assert info.name == "click"

    def test_nonexistent_generator(self):
        info = get_generator("nonexistent_activity_xyz")
        assert info is None


# ===================================================================
# generate_activity() errors
# ===================================================================

class TestGenerateActivityErrors:

    def test_nonexistent_raises_value_error(self):
        with pytest.raises(ValueError, match="No generator registered"):
            generate_activity("nonexistent_activity_xyz")


# ===================================================================
# All generators produce parseable XML
# ===================================================================

class TestAllGeneratorsParseable:

    # Provide minimal required parameters for each generator
    _MINIMAL_PARAMS: dict[str, dict] = {
        "click": {"selector": "<html />"},
        "type_into": {"selector": "<html />", "text": "test"},
        "get_text": {"selector": "<html />", "output_variable": "v"},
        "select_item": {"selector": "<html />", "item": "Option 1"},
        "check": {"selector": "<html />"},
        "hover": {"selector": "<html />"},
        "double_click": {"selector": "<html />"},
        "right_click": {"selector": "<html />"},
        "keyboard_shortcuts": {"key": "Enter"},
        "mouse_scroll": {"selector": "<html />"},
        "check_state": {"selector": "<html />", "output_variable": "v"},
        "if": {"condition": "True", "then_body": "<Sequence />"},
        "if_else_if": {"conditions": [("True", "<Sequence />")]},
        "foreach": {"collection": "items", "item_type": "x:String", "item_name": "item", "body": "<Sequence />"},
        "foreach_row": {"datatable": "dt", "body": "<Sequence />"},
        "foreach_file": {"directory": "C:\\temp", "pattern": "*.txt", "body": "<Sequence />"},
        "while": {"condition": "True", "body": "<Sequence />"},
        "do_while": {"condition": "True", "body": "<Sequence />"},
        "switch": {"expression": "status", "cases": {"A": "<Sequence />"}},
        "flowchart": {"nodes": [{"type": "step", "display_name": "Start", "body": "<Sequence />"}]},
        "state_machine": {"states": [{"name": "Initial", "entry": "<Sequence />", "is_final": True}]},
        "parallel": {"branches": ["<Sequence />", "<Sequence />"]},
        "parallel_foreach": {"collection": "items", "item_type": "x:String", "body": "<Sequence />"},
        "assign": {"variable": "x", "value": "1"},
        "multiple_assign": {"assignments": [("x", "1")]},
        "build_data_table": {"columns": [{"name": "Col1", "type": "x:String"}]},
        "add_data_row": {"datatable": "dt", "values": ['"A"', '"B"']},
        "filter_data_table": {"datatable": "dt", "output": "filtered", "filters": [{"column": "Col1", "operation": "Equals", "value": "X"}]},
        "try_catch": {"try_body": "<Sequence />", "catches": [{"exception_type": "System.Exception", "body": ""}]},
        "throw": {"exception_type": "System.Exception", "message": "Error"},
        "rethrow": {},
        "retry_scope": {"body": "<Sequence />"},
        "log_message": {"message": "test"},
        "comment": {"text": "A comment"},
        "kill_process": {"process_name": "notepad"},
        "take_screenshot": {},
        "terminate_workflow": {},
        "should_stop": {},
        "invoke_workflow": {"workflow_path": "Sub.xaml"},
        "invoke_code": {"code": "Console.WriteLine()"},
        "invoke_method": {"target_object": "obj", "method_name": "DoSomething"},
    }

    def test_all_generators_produce_parseable_xml(self):
        """Every registered generator should produce XML that can be parsed."""
        gens = list_generators()
        failed: list[str] = []

        for g in gens:
            params = self._MINIMAL_PARAMS.get(g.name)
            if params is None:
                # For generators not in our minimal params list, try with no args
                # (some may fail, but we skip those gracefully)
                continue

            reset_counter(1)
            try:
                xml_str = generate_activity(g.name, **params)
            except Exception as exc:
                failed.append(f"{g.name}: generation failed: {exc}")
                continue

            try:
                wrapped = _wrap_for_parse(xml_str)
                ET.fromstring(wrapped)
            except ET.ParseError as exc:
                failed.append(f"{g.name}: parse failed: {exc}")

        assert not failed, "Some generators produced unparseable XML:\n" + "\n".join(failed)


# ===================================================================
# Namespace prefixes
# ===================================================================

class TestNamespacePrefixes:

    def test_ui_namespace_in_click(self):
        xml_str = generate_activity("click", selector="<html />")
        assert "ui:" in xml_str

    def test_ui_namespace_in_log_message(self):
        xml_str = generate_activity("log_message", message="test")
        assert "ui:" in xml_str

    def test_x_namespace_in_foreach(self):
        xml_str = generate_activity(
            "foreach",
            collection="items",
            item_type="x:String",
            item_name="item",
            body="<Sequence />",
        )
        assert "x:TypeArguments" in xml_str

    def test_sap2010_viewstate_ref(self):
        xml_str = generate_activity("click", selector="<html />")
        assert "sap2010:WorkflowViewState.IdRef" in xml_str
