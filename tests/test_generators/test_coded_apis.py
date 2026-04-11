"""Tests for the Coded Automations API generators and coded workflow generator."""

from __future__ import annotations

import pytest

from rpa_architect.generators.base import reset_counter
from rpa_architect.generators.coded_apis import (
    gen_coded_add_queue_item,
    gen_coded_click,
    gen_coded_copy_file,
    gen_coded_get_asset,
    gen_coded_get_credential,
    gen_coded_get_queue_item,
    gen_coded_get_text,
    gen_coded_log_message,
    gen_coded_open_app,
    gen_coded_orchestrator_http_request,
    gen_coded_path_exists,
    gen_coded_read_text_file,
    gen_coded_set_asset,
    gen_coded_set_transaction_status,
    gen_coded_type_into,
    gen_coded_write_text_file,
)
from rpa_architect.generators.registry import get_generator
from rpa_architect.codegen.coded_workflow_gen import (
    generate_coded_workflow,
    generate_coded_test,
)


# ---------------------------------------------------------------------------
# Fixture: reset counter before each test for deterministic output
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_counter():
    reset_counter(1)
    yield
    reset_counter(1)


# ---------------------------------------------------------------------------
# System API generators
# ---------------------------------------------------------------------------

class TestGetAsset:
    def test_basic(self):
        result = gen_coded_get_asset("MyAsset", "val")
        assert result == 'var val = system.GetAsset("MyAsset");'

    def test_special_chars_in_name(self):
        result = gen_coded_get_asset("My/Asset & Co.", "x")
        assert 'system.GetAsset("My/Asset & Co.")' in result


class TestSetAsset:
    def test_basic(self):
        result = gen_coded_set_asset("Counter", "42")
        assert result == 'system.SetAsset("Counter", 42);'

    def test_string_value(self):
        result = gen_coded_set_asset("Name", '"hello"')
        assert result == 'system.SetAsset("Name", "hello");'


class TestGetCredential:
    def test_basic(self):
        result = gen_coded_get_credential("SAP_Login", "user", "pass")
        assert result == 'var (user, pass) = system.GetCredential("SAP_Login");'


class TestAddQueueItem:
    def test_basic(self):
        result = gen_coded_add_queue_item("InvoiceQueue", "dataRow")
        assert result == 'system.AddQueueItem("InvoiceQueue", dataRow);'


class TestGetQueueItem:
    def test_basic(self):
        result = gen_coded_get_queue_item("InvoiceQueue", "item")
        assert result == 'var item = system.GetQueueItem("InvoiceQueue");'


class TestSetTransactionStatus:
    def test_success(self):
        result = gen_coded_set_transaction_status("txn", "Success")
        assert "TransactionStatus.Success" in result
        assert result.startswith("system.SetTransactionStatus(txn,")

    def test_failed(self):
        result = gen_coded_set_transaction_status("item", "Failed")
        assert "TransactionStatus.Failed" in result


class TestLogMessage:
    def test_default_level(self):
        result = gen_coded_log_message("Processing started")
        assert result == 'Log("Processing started", LogLevel.Info);'

    def test_custom_level(self):
        result = gen_coded_log_message("Oops", level="Error")
        assert result == 'Log("Oops", LogLevel.Error);'


class TestReadTextFile:
    def test_basic(self):
        result = gen_coded_read_text_file("C:\\data\\input.txt", "content")
        assert result == 'var content = system.ReadTextFile("C:\\data\\input.txt");'


class TestWriteTextFile:
    def test_basic(self):
        result = gen_coded_write_text_file("output.csv", "csvData")
        assert result == 'system.WriteTextFile("output.csv", csvData);'


class TestCopyFile:
    def test_basic(self):
        result = gen_coded_copy_file("a.txt", "b.txt")
        assert result == 'system.CopyFile("a.txt", "b.txt");'


class TestPathExists:
    def test_basic(self):
        result = gen_coded_path_exists("/tmp/data", "exists")
        assert result == 'var exists = system.PathExists("/tmp/data");'


class TestOrchestratorHttpRequest:
    def test_basic(self):
        result = gen_coded_orchestrator_http_request("GET", "/odata/Robots", "resp")
        assert result == 'var resp = system.OrchestratorHTTPRequest("GET", "/odata/Robots");'


# ---------------------------------------------------------------------------
# UI Automation API generators
# ---------------------------------------------------------------------------

class TestOpenApp:
    def test_basic(self):
        result = gen_coded_open_app("Descriptors.Notepad", "app")
        assert result == "using var app = uiAutomation.Open(Descriptors.Notepad);"


class TestCodedClick:
    def test_basic(self):
        result = gen_coded_click("app", "SubmitButton")
        assert result == 'app.Click("SubmitButton");'


class TestCodedTypeInto:
    def test_basic(self):
        result = gen_coded_type_into("app", "UsernameField", "admin")
        assert result == 'app.TypeInto("UsernameField", "admin");'


class TestCodedGetText:
    def test_basic(self):
        result = gen_coded_get_text("app", "StatusLabel", "status")
        assert result == 'var status = app.GetText("StatusLabel");'


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------

class TestRegistration:
    def test_all_coded_apis_registered(self):
        names = [
            "coded_get_asset", "coded_set_asset", "coded_get_credential",
            "coded_add_queue_item", "coded_get_queue_item",
            "coded_set_transaction_status", "coded_log_message",
            "coded_read_text_file", "coded_write_text_file",
            "coded_copy_file", "coded_path_exists",
            "coded_orchestrator_http_request",
            "coded_open_app", "coded_click", "coded_type_into", "coded_get_text",
        ]
        for name in names:
            info = get_generator(name)
            assert info is not None, f"Generator '{name}' not registered"
            assert info.category == "Coded API"


# ---------------------------------------------------------------------------
# Coded workflow generator
# ---------------------------------------------------------------------------

class TestGenerateCodedWorkflow:
    def test_basic_structure(self):
        result = generate_coded_workflow(
            "MainWorkflow", "MyProject",
            ['var x = system.GetAsset("Foo");', 'Log("done", LogLevel.Info);'],
        )
        assert "using System;" in result
        assert "using UiPath.CodedWorkflows;" in result
        assert "namespace MyProject" in result
        assert "public class MainWorkflow : CodedWorkflow" in result
        assert "[Workflow]" in result
        assert "public void Execute()" in result
        assert 'system.GetAsset("Foo")' in result
        assert 'Log("done"' in result

    def test_custom_imports(self):
        result = generate_coded_workflow(
            "Wf", "Ns",
            ["// body"],
            imports=["using System.Linq;"],
        )
        assert "using System.Linq;" in result

    def test_empty_body(self):
        result = generate_coded_workflow("Wf", "Ns", [])
        assert "public void Execute()" in result
        # Should still have braces even with empty body
        assert "{" in result and "}" in result


class TestGenerateCodedTest:
    def test_basic_structure(self):
        result = generate_coded_test(
            "LoginTest", "MyProject",
            ['app.Click("Login");'],
        )
        assert "[TestCase]" in result
        assert "public void TestCase1()" in result
        assert "public class LoginTest : CodedWorkflow" in result
        assert 'app.Click("Login")' in result

    def test_custom_test_name(self):
        result = generate_coded_test(
            "SmokeTest", "Tests",
            ["// verify"],
            test_name="VerifyLogin",
        )
        assert "public void VerifyLogin()" in result

    def test_custom_imports(self):
        result = generate_coded_test(
            "T", "Ns", ["// x"],
            imports=["using Xunit;"],
        )
        assert "using Xunit;" in result
