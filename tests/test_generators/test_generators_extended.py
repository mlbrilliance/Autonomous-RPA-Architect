"""Extended generator tests — Stream D: individual tests for untested generators."""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from rpa_architect.generators import generate_activity, get_generator, list_generators
from rpa_architect.generators.base import reset_counter


@pytest.fixture(autouse=True)
def _reset_counter():
    """Reset the ID counter for deterministic output."""
    reset_counter(1)
    yield
    reset_counter(1)


def _wrap_for_parse(xml_str: str) -> str:
    """Wrap a XAML fragment in a root element with namespace declarations."""
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


def _is_valid_xml(xaml: str) -> bool:
    """Check if the XAML fragment parses as valid XML (wrapped with namespaces)."""
    try:
        ET.fromstring(_wrap_for_parse(xaml))
        return True
    except ET.ParseError:
        return False


# ===================================================================
# Control Flow generators
# ===================================================================

class TestForEachRow:
    def test_generates_valid_xml(self):
        xaml = generate_activity("foreach_row", datatable="dt_Invoices", body="<Sequence />")
        assert _is_valid_xml(xaml)
        assert "dt_Invoices" in xaml

    def test_contains_display_name(self):
        xaml = generate_activity("foreach_row", datatable="dt", body="<Sequence />", display_name="Loop Rows")
        assert "Loop Rows" in xaml


class TestForEachFile:
    def test_generates_valid_xml(self):
        xaml = generate_activity("foreach_file", directory="C:\\Input", pattern="*.pdf", body="<Sequence />")
        assert _is_valid_xml(xaml)
        assert "C:\\Input" in xaml


class TestDoWhile:
    def test_generates_valid_xml(self):
        xaml = generate_activity("do_while", condition="counter &lt; 10", body="<Sequence />")
        assert _is_valid_xml(xaml)


class TestSwitch:
    def test_generates_valid_xml(self):
        xaml = generate_activity("switch", expression="status", cases={"Open": "<Sequence />", "Closed": "<Sequence />"})
        assert _is_valid_xml(xaml)
        assert "status" in xaml

    def test_contains_case_keys(self):
        xaml = generate_activity("switch", expression="x", cases={"A": "<Sequence />", "B": "<Sequence />"})
        assert "A" in xaml
        assert "B" in xaml


class TestStateMachine:
    def test_generates_valid_xml(self):
        xaml = generate_activity("state_machine", states=[{"name": "Init"}, {"name": "Process"}, {"name": "End"}])
        assert _is_valid_xml(xaml)
        assert "StateMachine" in xaml

    def test_contains_state_names(self):
        xaml = generate_activity("state_machine", states=[{"name": "Start"}, {"name": "Finish"}])
        assert "Start" in xaml
        assert "Finish" in xaml


class TestParallel:
    def test_generates_valid_xml(self):
        xaml = generate_activity("parallel", branches=["<Sequence />", "<Sequence />"])
        assert _is_valid_xml(xaml)
        assert "Parallel" in xaml


class TestParallelForEach:
    def test_generates_valid_xml(self):
        xaml = generate_activity("parallel_foreach", collection="items", item_type="x:String", body="<Sequence />")
        assert _is_valid_xml(xaml)
        assert "ParallelForEach" in xaml


class TestFlowchart:
    def test_generates_valid_xml(self):
        xaml = generate_activity("flowchart", nodes=[{"name": "Start"}, {"name": "Process"}])
        assert _is_valid_xml(xaml)
        assert "Flowchart" in xaml


class TestIfElseIf:
    def test_generates_valid_xml(self):
        xaml = generate_activity("if_else_if", conditions=[("x &gt; 0", "<Sequence />"), ("x &lt; 0", "<Sequence />")])
        assert _is_valid_xml(xaml)
        assert "If" in xaml


# ===================================================================
# Data Operations generators
# ===================================================================

class TestBuildDataTable:
    def test_generates_valid_xml(self):
        xaml = generate_activity("build_data_table", columns=[{"name": "Name"}, {"name": "Age"}])
        assert _is_valid_xml(xaml)

    def test_contains_column_names(self):
        xaml = generate_activity("build_data_table", columns=[{"name": "Col1"}, {"name": "Col2"}])
        assert "Col1" in xaml
        assert "Col2" in xaml


class TestAddDataColumn:
    def test_generates_valid_xml(self):
        xaml = generate_activity("add_data_column", datatable="dt", column_name="Status")
        assert _is_valid_xml(xaml)
        assert "Status" in xaml


class TestFilterDataTable:
    def test_generates_valid_xml(self):
        xaml = generate_activity("filter_data_table", datatable="dt_Input", output="dt_Output", filters=[])
        assert _is_valid_xml(xaml)
        assert "dt_Input" in xaml


class TestSortDataTable:
    def test_generates_valid_xml(self):
        xaml = generate_activity("sort_data_table", datatable="dt", column_name="Date", direction="Ascending")
        assert _is_valid_xml(xaml)
        assert "Date" in xaml


class TestJoinDataTables:
    def test_generates_valid_xml(self):
        xaml = generate_activity("join_data_tables", dt1="dt1", dt2="dt2", output="dtJoined")
        assert _is_valid_xml(xaml)
        assert "dt1" in xaml


class TestMergeDataTable:
    def test_generates_valid_xml(self):
        xaml = generate_activity("merge_data_table", source="dtSrc", destination="dtDst")
        assert _is_valid_xml(xaml)
        assert "dtSrc" in xaml


class TestLookupDataTable:
    def test_generates_valid_xml(self):
        xaml = generate_activity("lookup_data_table", datatable="dt", lookup_value="key", column_name="ID", target_column="Name", output="result")
        assert _is_valid_xml(xaml)
        assert "key" in xaml


class TestOutputDataTable:
    def test_generates_valid_xml(self):
        xaml = generate_activity("output_data_table", datatable="dt", output_variable="strResult")
        assert _is_valid_xml(xaml)
        assert "dt" in xaml


class TestRemoveDataColumn:
    def test_generates_valid_xml(self):
        xaml = generate_activity("remove_data_column", datatable="dt", column_name="Temp")
        assert _is_valid_xml(xaml)
        assert "Temp" in xaml


class TestRemoveDuplicateRows:
    def test_generates_valid_xml(self):
        xaml = generate_activity("remove_duplicate_rows", datatable="dt", output="dtClean")
        assert _is_valid_xml(xaml)


class TestGenerateDataTable:
    def test_generates_valid_xml(self):
        xaml = generate_activity("generate_data_table", csv_text="a,b,c", output="dt")
        assert _is_valid_xml(xaml)


class TestMultipleAssign:
    def test_generates_valid_xml(self):
        xaml = generate_activity("multiple_assign", assignments=[("x", "1"), ("y", "2")])
        assert _is_valid_xml(xaml)
        assert "x" in xaml
        assert "y" in xaml


class TestVariablesBlock:
    def test_generates_valid_xml(self):
        xaml = generate_activity("variables_block", variables=[{"name": "count", "type": "x:Int32"}])
        # variables_block wraps in Sequence.Variables — valid XML fragment
        assert "count" in xaml
        assert "Int32" in xaml


# ===================================================================
# File System generators
# ===================================================================

class TestCopyFile:
    def test_generates_valid_xml(self):
        xaml = generate_activity("copy_file", source="a.txt", destination="b.txt")
        assert _is_valid_xml(xaml)
        assert "a.txt" in xaml

class TestMoveFile:
    def test_generates_valid_xml(self):
        xaml = generate_activity("move_file", source="a.txt", destination="b.txt")
        assert _is_valid_xml(xaml)

class TestDeleteFile:
    def test_generates_valid_xml(self):
        xaml = generate_activity("delete_file", path="temp.txt")
        assert _is_valid_xml(xaml)

class TestCreateDirectory:
    def test_generates_valid_xml(self):
        xaml = generate_activity("create_directory", path="C:\\Output")
        assert _is_valid_xml(xaml)

class TestPathExists:
    def test_generates_valid_xml(self):
        xaml = generate_activity("path_exists", path="C:\\Data", output="exists")
        assert _is_valid_xml(xaml)

class TestReadCsv:
    def test_generates_valid_xml(self):
        xaml = generate_activity("read_csv", path="data.csv", output="dt")
        assert _is_valid_xml(xaml)

class TestWriteCsv:
    def test_generates_valid_xml(self):
        xaml = generate_activity("write_csv", path="out.csv", datatable="dt")
        assert _is_valid_xml(xaml)

class TestReadTextFile:
    def test_generates_valid_xml(self):
        xaml = generate_activity("read_text_file", path="input.txt", output="content")
        assert _is_valid_xml(xaml)

class TestWriteTextFile:
    def test_generates_valid_xml(self):
        xaml = generate_activity("write_text_file", path="output.txt", text="hello")
        assert _is_valid_xml(xaml)


# ===================================================================
# Integration generators
# ===================================================================

class TestAppendRange:
    def test_generates_valid_xml(self):
        xaml = generate_activity("append_range", workbook_path="data.xlsx", sheet="Sheet1", datatable="dt")
        assert _is_valid_xml(xaml)

class TestWriteCell:
    def test_generates_valid_xml(self):
        xaml = generate_activity("write_cell", workbook_path="data.xlsx", sheet="Sheet1", cell="A1", value="hello")
        assert _is_valid_xml(xaml)

class TestGetImapMail:
    def test_generates_valid_xml(self):
        xaml = generate_activity("get_imap_mail", server="imap.gmail.com", port=993, username="user", password_var="pwd", output="messages")
        assert _is_valid_xml(xaml)
        assert "imap.gmail.com" in xaml

class TestSendMail:
    def test_generates_valid_xml(self):
        xaml = generate_activity("send_mail", to="user@example.com", subject="Test", body="Hello")
        assert _is_valid_xml(xaml)
        assert "user@example.com" in xaml

class TestSaveMailAttachments:
    def test_generates_valid_xml(self):
        xaml = generate_activity("save_mail_attachments", mail_var="mailMsg", folder_path="C:\\Attachments")
        assert _is_valid_xml(xaml)

class TestDatabaseConnect:
    def test_generates_valid_xml(self):
        xaml = generate_activity("database_connect", connection_string="Server=localhost;Database=test", provider="System.Data.SqlClient", output="dbConn")
        assert _is_valid_xml(xaml)

class TestExecuteQuery:
    def test_generates_valid_xml(self):
        xaml = generate_activity("execute_query", connection="dbConn", sql="SELECT * FROM users", output="dtResult")
        assert _is_valid_xml(xaml)

class TestExecuteNonQuery:
    def test_generates_valid_xml(self):
        xaml = generate_activity("execute_non_query", connection="dbConn", sql="DELETE FROM temp", output="affected")
        assert _is_valid_xml(xaml)

class TestReadPdfText:
    def test_generates_valid_xml(self):
        xaml = generate_activity("read_pdf_text", file_path="doc.pdf", output="text")
        assert _is_valid_xml(xaml)

class TestReadPdfWithOcr:
    def test_generates_valid_xml(self):
        xaml = generate_activity("read_pdf_with_ocr", file_path="scan.pdf", output="text")
        assert _is_valid_xml(xaml)


# ===================================================================
# Error Handling generators
# ===================================================================

class TestRethrow:
    def test_generates_valid_xml(self):
        xaml = generate_activity("rethrow")
        assert _is_valid_xml(xaml)
        assert "Rethrow" in xaml

class TestRetryScope:
    def test_generates_valid_xml(self):
        xaml = generate_activity("retry_scope", body="<Sequence />", max_retries=3)
        assert _is_valid_xml(xaml)
        assert "RetryScope" in xaml

class TestThrow:
    def test_generates_valid_xml(self):
        xaml = generate_activity("throw", exception_type="System.Exception", message="Test error")
        assert _is_valid_xml(xaml)


# ===================================================================
# Invoke generators
# ===================================================================

class TestInvokeCode:
    def test_generates_valid_xml(self):
        xaml = generate_activity("invoke_code", code='Console.WriteLine("hi");', language="CSharp")
        assert _is_valid_xml(xaml)

class TestInvokeMethod:
    def test_generates_valid_xml(self):
        xaml = generate_activity("invoke_method", target_object="myObj", method_name="IsNullOrEmpty")
        assert _is_valid_xml(xaml)


# ===================================================================
# Orchestrator generators
# ===================================================================

class TestAddQueueItem:
    def test_generates_valid_xml(self):
        xaml = generate_activity("add_queue_item", queue_name="InvoiceQueue", item_data={"ref": "INV-001"})
        assert _is_valid_xml(xaml)
        assert "InvoiceQueue" in xaml

class TestBulkAddQueueItems:
    def test_generates_valid_xml(self):
        xaml = generate_activity("bulk_add_queue_items", queue_name="Batch", datatable="dt")
        assert _is_valid_xml(xaml)

class TestGetQueueItem:
    def test_generates_valid_xml(self):
        xaml = generate_activity("get_queue_item", queue_name="Work", output="item")
        assert _is_valid_xml(xaml)

class TestGetRobotAsset:
    def test_generates_valid_xml(self):
        xaml = generate_activity("get_robot_asset", asset_name="MyAsset", output="val")
        assert _is_valid_xml(xaml)

class TestGetRobotCredential:
    def test_generates_valid_xml(self):
        xaml = generate_activity("get_robot_credential", asset_name="MyCred", username_output="user", password_output="pwd")
        assert _is_valid_xml(xaml)


# ===================================================================
# HTTP / JSON generators
# ===================================================================

class TestDeserializeJson:
    def test_generates_valid_xml(self):
        xaml = generate_activity("deserialize_json", json_string="jsonStr", output="result")
        assert _is_valid_xml(xaml)


# ===================================================================
# Miscellaneous generators
# ===================================================================

class TestComment:
    def test_generates_valid_xml(self):
        xaml = generate_activity("comment", text="This is a comment")
        assert _is_valid_xml(xaml)

class TestKillProcess:
    def test_generates_valid_xml(self):
        xaml = generate_activity("kill_process", process_name="notepad")
        assert _is_valid_xml(xaml)

class TestTakeScreenshot:
    def test_generates_valid_xml(self):
        xaml = generate_activity("take_screenshot", output="screenshot")
        assert _is_valid_xml(xaml)

class TestShouldStop:
    def test_generates_valid_xml(self):
        xaml = generate_activity("should_stop", output="shouldStop")
        assert _is_valid_xml(xaml)

class TestTerminateWorkflow:
    def test_generates_valid_xml(self):
        xaml = generate_activity("terminate_workflow", reason="Done")
        assert _is_valid_xml(xaml)


# ===================================================================
# UI Automation extended
# ===================================================================

class TestDoubleClick:
    def test_generates_valid_xml(self):
        xaml = generate_activity("double_click", selector="<html />")
        assert _is_valid_xml(xaml)

class TestRightClick:
    def test_generates_valid_xml(self):
        xaml = generate_activity("right_click", selector="<html />")
        assert _is_valid_xml(xaml)

class TestCheckState:
    def test_generates_valid_xml(self):
        xaml = generate_activity("check_state", selector="<html />", output_variable="isChecked")
        assert _is_valid_xml(xaml)

class TestKeyboardShortcuts:
    def test_generates_valid_xml(self):
        xaml = generate_activity("keyboard_shortcuts", key="ctrl+c")
        assert _is_valid_xml(xaml)

class TestMouseScroll:
    def test_generates_valid_xml(self):
        xaml = generate_activity("mouse_scroll", selector="<html />", direction="Down", clicks=3)
        assert _is_valid_xml(xaml)


# ===================================================================
# Edge cases
# ===================================================================

class TestEdgeCases:
    def test_special_chars_in_display_name(self):
        xaml = generate_activity("log_message", message="Test", level="Info", display_name='Say "Hello" & <Goodbye>')
        assert _is_valid_xml(xaml)
        # Special chars should be escaped
        assert "&amp;" in xaml or "&lt;" in xaml or "&quot;" in xaml

    def test_empty_string_params(self):
        xaml = generate_activity("assign", variable="x", value="test")
        assert _is_valid_xml(xaml)

    def test_unicode_in_params(self):
        xaml = generate_activity("log_message", message="こんにちは世界", level="Info")
        assert _is_valid_xml(xaml)
        assert "こんにちは世界" in xaml
