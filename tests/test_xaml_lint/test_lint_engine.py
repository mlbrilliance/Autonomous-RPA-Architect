"""Tests for the XAML hallucination linter."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from rpa_architect.xaml_lint import (
    LintCategory,
    LintEngine,
    LintIssue,
    LintResult,
    LintSeverity,
    lint_project,
    lint_xaml,
)
from rpa_architect.xaml_lint.engine import LintEngine, create_default_engine


# ---------------------------------------------------------------------------
# Shared XAML templates
# ---------------------------------------------------------------------------

VALID_XAML = """\
<?xml version="1.0" encoding="utf-8"?>
<Activity mc:Ignorable="sap sap2010 sads"
  x:Class="Main"
  xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
  xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
  xmlns:sap="http://schemas.microsoft.com/netfx/2009/xaml/activities/presentation"
  xmlns:sap2010="http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation"
  xmlns:sads="http://schemas.microsoft.com/netfx/2010/xaml/activities/debugger"
  xmlns:scg="clr-namespace:System.Collections.Generic;assembly=mscorlib"
  xmlns:ui="http://schemas.uipath.com/workflow/activities"
  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName="Main">
    <ui:LogMessage DisplayName="Log Message" Level="Info" Message="Hello" />
  </Sequence>
</Activity>
"""

MINIMAL_VALID_XAML = """\
<?xml version="1.0" encoding="utf-8"?>
<Activity
  xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
  xmlns:ui="http://schemas.uipath.com/workflow/activities"
  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName="Main">
    <Assign DisplayName="Set Variable">
      <Assign.To>
        <OutArgument x:TypeArguments="x:String">[result]</OutArgument>
      </Assign.To>
      <Assign.Value>
        <InArgument x:TypeArguments="x:String">"Hello"</InArgument>
      </Assign.Value>
    </Assign>
  </Sequence>
</Activity>
"""


# ===================================================================
# lint_xaml() -- valid XAML
# ===================================================================

class TestLintXamlValid:
    """Tests that valid XAML returns no ERROR-level issues."""

    def test_valid_xaml_no_errors(self):
        issues = lint_xaml(VALID_XAML)
        errors = [i for i in issues if i.severity == LintSeverity.ERROR]
        assert errors == [], f"Unexpected errors: {errors}"

    def test_minimal_valid_xaml_no_errors(self):
        issues = lint_xaml(MINIMAL_VALID_XAML)
        errors = [i for i in issues if i.severity == LintSeverity.ERROR]
        assert errors == [], f"Unexpected errors: {errors}"

    def test_issues_are_sorted(self):
        """Returned issues should be sorted: ERROR first, then WARNING, then INFO."""
        issues = lint_xaml(VALID_XAML)
        severities = [i.severity for i in issues]
        order = {LintSeverity.ERROR: 0, LintSeverity.WARNING: 1, LintSeverity.INFO: 2}
        numeric = [order[s] for s in severities]
        assert numeric == sorted(numeric), "Issues not sorted by severity"


# ===================================================================
# lint_xaml() -- invalid XML (parse error)
# ===================================================================

class TestLintXamlParseError:

    def test_invalid_xml_returns_parse_error(self):
        issues = lint_xaml("<Unclosed>")
        assert len(issues) == 1
        issue = issues[0]
        assert issue.rule_id == "XL-PARSE"
        assert issue.severity == LintSeverity.ERROR
        assert issue.category == LintCategory.HALLUCINATION
        assert "parse error" in issue.message.lower()

    def test_completely_broken_xml(self):
        issues = lint_xaml("<<<not xml at all>>>")
        assert any(i.rule_id == "XL-PARSE" for i in issues)

    def test_empty_content(self):
        """Empty content is not valid XML, so should get a parse error."""
        issues = lint_xaml("")
        # Empty string will cause a parse error
        assert len(issues) >= 1
        assert issues[0].rule_id == "XL-PARSE"


# ===================================================================
# XL-H001: Unknown activities
# ===================================================================

class TestUnknownActivities:

    def test_unknown_activity_flagged(self):
        xaml = """\
<?xml version="1.0" encoding="utf-8"?>
<Activity
  xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
  xmlns:ui="http://schemas.uipath.com/workflow/activities"
  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName="Main">
    <FakeActivity DisplayName="I do not exist" />
  </Sequence>
</Activity>
"""
        issues = lint_xaml(xaml)
        h001 = [i for i in issues if i.rule_id == "XL-H001"]
        assert len(h001) >= 1
        assert any("FakeActivity" in i.message for i in h001)

    def test_invented_read_excel_flagged(self):
        """LLMs often invent 'ReadExcel' instead of 'ReadRange'."""
        xaml = """\
<?xml version="1.0" encoding="utf-8"?>
<Activity
  xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
  xmlns:ui="http://schemas.uipath.com/workflow/activities"
  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName="Main">
    <ReadExcel DisplayName="Read Excel" />
  </Sequence>
</Activity>
"""
        issues = lint_xaml(xaml)
        h001 = [i for i in issues if i.rule_id == "XL-H001"]
        assert any("ReadExcel" in i.message for i in h001)

    def test_known_activities_not_flagged(self):
        """Standard activities like Sequence, Assign, If should not be flagged."""
        xaml = """\
<?xml version="1.0" encoding="utf-8"?>
<Activity
  xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
  xmlns:ui="http://schemas.uipath.com/workflow/activities"
  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName="Main">
    <If Condition="[True]" DisplayName="Check">
      <If.Then>
        <Assign DisplayName="Set Var">
          <Assign.To>
            <OutArgument x:TypeArguments="x:String">[x]</OutArgument>
          </Assign.To>
          <Assign.Value>
            <InArgument x:TypeArguments="x:String">"yes"</InArgument>
          </Assign.Value>
        </Assign>
      </If.Then>
    </If>
  </Sequence>
</Activity>
"""
        issues = lint_xaml(xaml)
        h001 = [i for i in issues if i.rule_id == "XL-H001"]
        assert h001 == []


# ===================================================================
# XL-H003: Invalid enum values
# ===================================================================

class TestInvalidEnumValues:

    def test_invalid_click_type_flagged(self):
        xaml = """\
<?xml version="1.0" encoding="utf-8"?>
<Activity
  xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
  xmlns:ui="http://schemas.uipath.com/workflow/activities"
  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName="Main">
    <ui:NClick ClickType="WRONG_VALUE" DisplayName="Click" />
  </Sequence>
</Activity>
"""
        issues = lint_xaml(xaml)
        h003 = [i for i in issues if i.rule_id == "XL-H003"]
        assert len(h003) >= 1
        assert any("WRONG_VALUE" in i.message for i in h003)

    def test_valid_click_type_not_flagged(self):
        xaml = """\
<?xml version="1.0" encoding="utf-8"?>
<Activity
  xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
  xmlns:ui="http://schemas.uipath.com/workflow/activities"
  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName="Main">
    <ui:NClick ClickType="CLICK_SINGLE" MouseButton="BTN_LEFT" DisplayName="Click" />
  </Sequence>
</Activity>
"""
        issues = lint_xaml(xaml)
        h003 = [i for i in issues if i.rule_id == "XL-H003"]
        assert h003 == []

    def test_invalid_log_level_flagged(self):
        xaml = """\
<?xml version="1.0" encoding="utf-8"?>
<Activity
  xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
  xmlns:ui="http://schemas.uipath.com/workflow/activities"
  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName="Main">
    <ui:LogMessage Level="Debug" Message="test" DisplayName="Log" />
  </Sequence>
</Activity>
"""
        issues = lint_xaml(xaml)
        h003 = [i for i in issues if i.rule_id == "XL-H003"]
        # "Debug" is not a valid Level value (should be Trace, Info, Warn, Error, Fatal)
        assert len(h003) >= 1


# ===================================================================
# XL-H004: Wrong nesting
# ===================================================================

class TestWrongNesting:

    def test_if_missing_then_flagged(self):
        xaml = """\
<?xml version="1.0" encoding="utf-8"?>
<Activity
  xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
  xmlns:ui="http://schemas.uipath.com/workflow/activities"
  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName="Main">
    <If Condition="[True]" DisplayName="Bad If">
    </If>
  </Sequence>
</Activity>
"""
        issues = lint_xaml(xaml)
        h004 = [i for i in issues if i.rule_id == "XL-H004"]
        assert len(h004) >= 1
        assert any("If" in i.message for i in h004)

    def test_trycatch_missing_catches_flagged(self):
        xaml = """\
<?xml version="1.0" encoding="utf-8"?>
<Activity
  xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
  xmlns:ui="http://schemas.uipath.com/workflow/activities"
  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName="Main">
    <TryCatch DisplayName="Try">
      <TryCatch.Try>
        <Sequence DisplayName="Body">
          <ui:LogMessage Level="Info" Message="Try" DisplayName="Log" />
        </Sequence>
      </TryCatch.Try>
    </TryCatch>
  </Sequence>
</Activity>
"""
        issues = lint_xaml(xaml)
        h004 = [i for i in issues if i.rule_id == "XL-H004"]
        assert any("Catches" in i.message for i in h004)

    def test_correct_nesting_no_issues(self):
        xaml = """\
<?xml version="1.0" encoding="utf-8"?>
<Activity
  xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
  xmlns:ui="http://schemas.uipath.com/workflow/activities"
  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName="Main">
    <If Condition="[True]" DisplayName="Good If">
      <If.Then>
        <Assign DisplayName="Assign">
          <Assign.To>
            <OutArgument x:TypeArguments="x:String">[x]</OutArgument>
          </Assign.To>
          <Assign.Value>
            <InArgument x:TypeArguments="x:String">"yes"</InArgument>
          </Assign.Value>
        </Assign>
      </If.Then>
    </If>
  </Sequence>
</Activity>
"""
        issues = lint_xaml(xaml)
        h004 = [i for i in issues if i.rule_id == "XL-H004"]
        assert h004 == []


# ===================================================================
# XL-B001: Hardcoded URLs
# ===================================================================

class TestHardcodedUrls:

    def test_hardcoded_url_flagged(self):
        xaml = """\
<?xml version="1.0" encoding="utf-8"?>
<Activity
  xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
  xmlns:ui="http://schemas.uipath.com/workflow/activities"
  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName="Main">
    <Assign DisplayName="Set URL">
      <Assign.To>
        <OutArgument x:TypeArguments="x:String">[url]</OutArgument>
      </Assign.To>
      <Assign.Value>
        <InArgument x:TypeArguments="x:String">"https://myapp.example.com/api/v1"</InArgument>
      </Assign.Value>
    </Assign>
  </Sequence>
</Activity>
"""
        issues = lint_xaml(xaml)
        b001 = [i for i in issues if i.rule_id == "XL-B001"]
        assert len(b001) >= 1
        assert any("myapp.example.com" in i.message for i in b001)

    def test_schema_urls_not_flagged(self):
        """Standard namespace/schema URLs should not be reported."""
        issues = lint_xaml(VALID_XAML)
        b001 = [i for i in issues if i.rule_id == "XL-B001"]
        assert b001 == []


# ===================================================================
# XL-S001: String password variables
# ===================================================================

class TestStringPasswords:

    def test_string_password_variable_flagged(self):
        xaml = """\
<?xml version="1.0" encoding="utf-8"?>
<Activity
  xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
  xmlns:ui="http://schemas.uipath.com/workflow/activities"
  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName="Main">
    <Sequence.Variables>
      <Variable x:TypeArguments="x:String" Name="userPassword" />
    </Sequence.Variables>
    <ui:LogMessage Level="Info" Message="done" DisplayName="Log" />
  </Sequence>
</Activity>
"""
        issues = lint_xaml(xaml)
        s001 = [i for i in issues if i.rule_id == "XL-S001"]
        assert len(s001) >= 1
        assert any("userPassword" in i.message for i in s001)

    def test_secure_string_password_not_flagged(self):
        xaml = """\
<?xml version="1.0" encoding="utf-8"?>
<Activity
  xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
  xmlns:ui="http://schemas.uipath.com/workflow/activities"
  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName="Main">
    <Sequence.Variables>
      <Variable x:TypeArguments="System.Security.SecureString" Name="userPassword" />
    </Sequence.Variables>
    <ui:LogMessage Level="Info" Message="done" DisplayName="Log" />
  </Sequence>
</Activity>
"""
        issues = lint_xaml(xaml)
        s001 = [i for i in issues if i.rule_id == "XL-S001"]
        assert s001 == []


# ===================================================================
# Empty content
# ===================================================================

class TestEmptyContent:

    def test_empty_string_returns_parse_issue(self):
        issues = lint_xaml("")
        assert len(issues) >= 1
        assert issues[0].severity == LintSeverity.ERROR

    def test_whitespace_only_returns_parse_issue(self):
        issues = lint_xaml("   \n\n  ")
        assert len(issues) >= 1
        assert issues[0].rule_id == "XL-PARSE"


# ===================================================================
# lint_project()
# ===================================================================

class TestLintProject:

    def test_lint_project_on_directory_with_xaml(self, tmp_path: Path):
        xaml_dir = tmp_path / "MyProject"
        xaml_dir.mkdir()
        (xaml_dir / "Main.xaml").write_text(VALID_XAML, encoding="utf-8")
        (xaml_dir / "Sub.xaml").write_text(MINIMAL_VALID_XAML, encoding="utf-8")

        results = lint_project(xaml_dir)
        assert len(results) == 2
        for r in results:
            assert isinstance(r, LintResult)
            assert r.file_path
            errors = [i for i in r.issues if i.severity == LintSeverity.ERROR]
            assert errors == []

    def test_lint_project_empty_directory(self, tmp_path: Path):
        empty_dir = tmp_path / "EmptyProject"
        empty_dir.mkdir()

        results = lint_project(empty_dir)
        assert len(results) == 1
        assert results[0].issues[0].rule_id == "XL-IO"
        assert results[0].issues[0].severity == LintSeverity.WARNING

    def test_lint_project_nonexistent_directory(self, tmp_path: Path):
        fake_dir = tmp_path / "DoesNotExist"

        results = lint_project(fake_dir)
        assert len(results) == 1
        assert results[0].issues[0].rule_id == "XL-IO"
        assert results[0].issues[0].severity == LintSeverity.ERROR

    def test_lint_project_recursive(self, tmp_path: Path):
        """XAML files in subdirectories should also be linted."""
        project_dir = tmp_path / "Project"
        project_dir.mkdir()
        sub = project_dir / "Workflows"
        sub.mkdir()
        (sub / "Process.xaml").write_text(VALID_XAML, encoding="utf-8")

        results = lint_project(project_dir)
        assert len(results) == 1
        assert "Workflows" in results[0].file_path


# ===================================================================
# LintEngine -- custom rules
# ===================================================================

class TestLintEngineCustomRules:

    def test_register_and_run_custom_rule(self):
        engine = LintEngine()

        def my_custom_rule(root, ns):
            return [
                LintIssue(
                    rule_id="XL-CUSTOM-001",
                    severity=LintSeverity.INFO,
                    category=LintCategory.BEST_PRACTICE,
                    message="Custom rule triggered",
                )
            ]

        engine.register_rule(my_custom_rule)
        assert engine.rule_count == 1

        issues = engine.run(VALID_XAML)
        assert any(i.rule_id == "XL-CUSTOM-001" for i in issues)

    def test_engine_rule_exception_does_not_crash(self):
        engine = LintEngine()

        def bad_rule(root, ns):
            raise RuntimeError("Intentional error")

        engine.register_rule(bad_rule)
        issues = engine.run(VALID_XAML)
        # The engine catches the error and reports an XL-INTERNAL issue
        assert any(i.rule_id == "XL-INTERNAL" for i in issues)

    def test_create_default_engine_has_rules(self):
        engine = create_default_engine()
        assert engine.rule_count > 0

    def test_multiple_custom_rules(self):
        engine = LintEngine()

        def rule_a(root, ns):
            return [
                LintIssue(
                    rule_id="XL-A",
                    severity=LintSeverity.INFO,
                    category=LintCategory.BEST_PRACTICE,
                    message="Rule A",
                )
            ]

        def rule_b(root, ns):
            return [
                LintIssue(
                    rule_id="XL-B",
                    severity=LintSeverity.WARNING,
                    category=LintCategory.SECURITY,
                    message="Rule B",
                )
            ]

        engine.register_rule(rule_a)
        engine.register_rule(rule_b)
        assert engine.rule_count == 2

        issues = engine.run(VALID_XAML)
        rule_ids = {i.rule_id for i in issues}
        assert "XL-A" in rule_ids
        assert "XL-B" in rule_ids


# ===================================================================
# LintResult model
# ===================================================================

class TestLintResultModel:

    def test_counts_computed_correctly(self):
        result = LintResult(
            file_path="test.xaml",
            issues=[
                LintIssue(rule_id="A", severity=LintSeverity.ERROR,
                          category=LintCategory.HALLUCINATION, message="e1"),
                LintIssue(rule_id="B", severity=LintSeverity.ERROR,
                          category=LintCategory.HALLUCINATION, message="e2"),
                LintIssue(rule_id="C", severity=LintSeverity.WARNING,
                          category=LintCategory.SECURITY, message="w1"),
                LintIssue(rule_id="D", severity=LintSeverity.INFO,
                          category=LintCategory.BEST_PRACTICE, message="i1"),
            ],
        )
        assert result.error_count == 2
        assert result.warning_count == 1
        assert result.info_count == 1

    def test_empty_result(self):
        result = LintResult(file_path="empty.xaml", issues=[])
        assert result.error_count == 0
        assert result.warning_count == 0
        assert result.info_count == 0
