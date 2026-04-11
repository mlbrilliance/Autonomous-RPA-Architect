"""Tests for C# coded workflow lint rules."""

from __future__ import annotations

import pytest

from rpa_architect.xaml_lint.models import LintSeverity
from rpa_architect.xaml_lint.rules_coded import (
    _check_hardcoded_orchestrator_url,
    _check_missing_using_directives,
    _check_missing_workflow_attribute,
    _check_unsafe_credential_handling,
    lint_coded_file,
)


# ---------------------------------------------------------------------------
# XL-C001: Missing [Workflow] attribute
# ---------------------------------------------------------------------------

class TestXLC001:
    MISSING_ATTR = """\
using UiPath.CodedWorkflows;

public class MyWorkflow : CodedWorkflow
{
    public void Execute()
    {
    }
}
"""

    HAS_ATTR = """\
using UiPath.CodedWorkflows;

public class MyWorkflow : CodedWorkflow
{
    [Workflow]
    public void Execute()
    {
    }
}
"""

    def test_detects_missing_attribute(self):
        issues = _check_missing_workflow_attribute(self.MISSING_ATTR)
        assert len(issues) == 1
        assert issues[0].rule_id == "XL-C001"
        assert issues[0].severity == LintSeverity.ERROR

    def test_passes_when_attribute_present(self):
        issues = _check_missing_workflow_attribute(self.HAS_ATTR)
        assert issues == []

    def test_no_issue_when_not_coded_workflow(self):
        issues = _check_missing_workflow_attribute("public class Foo { }")
        assert issues == []


# ---------------------------------------------------------------------------
# XL-C002: Hardcoded Orchestrator URL
# ---------------------------------------------------------------------------

class TestXLC002:
    def test_detects_orchestrator_url(self):
        code = 'var url = "https://myorg.orchestrator.cloud/api";'
        issues = _check_hardcoded_orchestrator_url(code)
        assert len(issues) == 1
        assert issues[0].rule_id == "XL-C002"
        assert issues[0].severity == LintSeverity.WARNING

    def test_detects_uipath_api_url(self):
        code = 'var url = "https://cloud.uipath.com/api/v1/robots";'
        issues = _check_hardcoded_orchestrator_url(code)
        assert len(issues) == 1
        assert issues[0].rule_id == "XL-C002"

    def test_no_issue_for_clean_code(self):
        code = 'var url = config.GetOrchestratorUrl();'
        issues = _check_hardcoded_orchestrator_url(code)
        assert issues == []


# ---------------------------------------------------------------------------
# XL-C003: Missing using directive
# ---------------------------------------------------------------------------

class TestXLC003:
    def test_detects_missing_using(self):
        code = "public class MyWorkflow : CodedWorkflow { }"
        issues = _check_missing_using_directives(code)
        assert len(issues) == 1
        assert issues[0].rule_id == "XL-C003"
        assert issues[0].severity == LintSeverity.ERROR

    def test_passes_with_using(self):
        code = """\
using UiPath.CodedWorkflows;
public class MyWorkflow : CodedWorkflow { }
"""
        issues = _check_missing_using_directives(code)
        assert issues == []


# ---------------------------------------------------------------------------
# XL-C004: Unsafe credential handling
# ---------------------------------------------------------------------------

class TestXLC004:
    def test_detects_string_password(self):
        code = 'string password = GetPassword();'
        issues = _check_unsafe_credential_handling(code)
        assert len(issues) == 1
        assert issues[0].rule_id == "XL-C004"
        assert issues[0].severity == LintSeverity.WARNING

    def test_detects_var_password_literal(self):
        code = 'var password = "mysecret123";'
        issues = _check_unsafe_credential_handling(code)
        assert len(issues) == 1
        assert issues[0].rule_id == "XL-C004"

    def test_no_issue_for_secure_string(self):
        code = "SecureString credential = sdk.GetCredential(\"MyAsset\");"
        issues = _check_unsafe_credential_handling(code)
        assert issues == []


# ---------------------------------------------------------------------------
# Full lint_coded_file integration
# ---------------------------------------------------------------------------

class TestLintCodedFile:
    def test_clean_code_passes_all(self):
        code = """\
using UiPath.CodedWorkflows;

public class MyWorkflow : CodedWorkflow
{
    [Workflow]
    public void Execute()
    {
        var url = config.GetUrl();
    }
}
"""
        issues = lint_coded_file(code)
        assert issues == []

    def test_multiple_issues_detected(self):
        code = """\
public class MyWorkflow : CodedWorkflow
{
    public void Execute()
    {
        string password = "test";
        var url = "https://cloud.uipath.com/api";
    }
}
"""
        issues = lint_coded_file(code)
        rule_ids = {i.rule_id for i in issues}
        # Should detect: XL-C001 (no [Workflow]), XL-C003 (no using),
        # XL-C004 (string password), XL-C002 (hardcoded URL)
        assert "XL-C001" in rule_ids
        assert "XL-C003" in rule_ids
        assert "XL-C004" in rule_ids
        assert "XL-C002" in rule_ids
