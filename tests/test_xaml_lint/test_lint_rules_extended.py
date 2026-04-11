"""Extended lint rule tests — Stream E: tests for 15 previously untested rules."""
from __future__ import annotations

import pytest

from rpa_architect.xaml_lint import lint_xaml, LintSeverity


# ---------------------------------------------------------------------------
# Shared XAML wrapper
# ---------------------------------------------------------------------------

def _wrap(body: str) -> str:
    """Wrap activity body in a valid XAML shell."""
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<Activity\n'
        '  xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"\n'
        '  xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"\n'
        '  xmlns:ui="http://schemas.uipath.com/workflow/activities"\n'
        '  xmlns:scg="clr-namespace:System.Collections.Generic;assembly=mscorlib"\n'
        '  xmlns:s="clr-namespace:System;assembly=mscorlib"\n'
        '  xmlns:sap2010="http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation"\n'
        '  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">\n'
        f'  <Sequence DisplayName="Main">\n{body}\n  </Sequence>\n'
        '</Activity>\n'
    )


# ===================================================================
# XL-H002: Missing namespace declarations
# ===================================================================

class TestMissingNamespaces:

    def test_undeclared_prefix_in_type_argument(self):
        xaml = _wrap(
            '    <ForEach TypeArgument="myns:CustomType" DisplayName="Loop">\n'
            '      <ForEach.Body>\n'
            '        <ActivityAction>\n'
            '          <Sequence DisplayName="Body" />\n'
            '        </ActivityAction>\n'
            '      </ForEach.Body>\n'
            '    </ForEach>'
        )
        issues = lint_xaml(xaml)
        h002 = [i for i in issues if i.rule_id == "XL-H002"]
        assert len(h002) >= 1
        assert any("myns" in i.message for i in h002)

    def test_declared_prefix_not_flagged(self):
        # x: and scg: are declared in _wrap — should not be flagged
        xaml = _wrap(
            '    <ForEach TypeArgument="scg:List(x:String)" DisplayName="Loop">\n'
            '      <ForEach.Body>\n'
            '        <ActivityAction>\n'
            '          <Sequence DisplayName="Body" />\n'
            '        </ActivityAction>\n'
            '      </ForEach.Body>\n'
            '    </ForEach>'
        )
        issues = lint_xaml(xaml)
        h002 = [i for i in issues if i.rule_id == "XL-H002"]
        assert h002 == []


# ===================================================================
# XL-H005: Nonexistent properties
# ===================================================================

class TestNonexistentProperties:

    def test_invalid_property_on_known_activity(self):
        # NClick has known valid properties; "Selector" is NOT one of them
        xaml = _wrap(
            '    <ui:NClick Selector="&lt;html /&gt;" DisplayName="Click" />'
        )
        issues = lint_xaml(xaml)
        h005 = [i for i in issues if i.rule_id == "XL-H005"]
        assert len(h005) >= 1
        assert any("Selector" in i.message for i in h005)

    def test_valid_property_not_flagged(self):
        xaml = _wrap(
            '    <ui:NClick ClickType="CLICK_SINGLE" DisplayName="Click" />'
        )
        issues = lint_xaml(xaml)
        h005 = [i for i in issues if i.rule_id == "XL-H005"]
        assert h005 == []


# ===================================================================
# XL-H006: Broken ViewState references
# ===================================================================

class TestBrokenViewState:

    def test_orphaned_viewstate_flagged(self):
        xaml = _wrap(
            '    <ui:LogMessage DisplayName="Log" Level="Info" Message="hi"'
            ' sap2010:WorkflowViewState.IdRef="Log_1" />\n'
            '    <WorkflowViewState>\n'
            '      <ViewStateData Id="Log_999" />\n'
            '    </WorkflowViewState>'
        )
        issues = lint_xaml(xaml)
        h006 = [i for i in issues if i.rule_id == "XL-H006"]
        assert len(h006) >= 1
        assert any("Log_999" in i.message for i in h006)

    def test_matching_viewstate_not_flagged(self):
        xaml = _wrap(
            '    <ui:LogMessage DisplayName="Log" Level="Info" Message="hi"'
            ' sap2010:WorkflowViewState.IdRef="Log_1" />\n'
            '    <WorkflowViewState>\n'
            '      <ViewStateData Id="Log_1" />\n'
            '    </WorkflowViewState>'
        )
        issues = lint_xaml(xaml)
        h006 = [i for i in issues if i.rule_id == "XL-H006"]
        assert h006 == []


# ===================================================================
# XL-H007: Invalid TypeArgument values
# ===================================================================

class TestInvalidTypeArguments:

    def test_nonsense_type_flagged(self):
        xaml = _wrap(
            '    <ForEach TypeArgument="FooBarBaz" DisplayName="Loop">\n'
            '      <ForEach.Body>\n'
            '        <ActivityAction>\n'
            '          <Sequence DisplayName="Body" />\n'
            '        </ActivityAction>\n'
            '      </ForEach.Body>\n'
            '    </ForEach>'
        )
        issues = lint_xaml(xaml)
        h007 = [i for i in issues if i.rule_id == "XL-H007"]
        assert len(h007) >= 1
        assert len(h007) >= 1

    def test_valid_type_not_flagged(self):
        xaml = _wrap(
            '    <ForEach TypeArgument="x:String" DisplayName="Loop">\n'
            '      <ForEach.Body>\n'
            '        <ActivityAction>\n'
            '          <Sequence DisplayName="Body" />\n'
            '        </ActivityAction>\n'
            '      </ForEach.Body>\n'
            '    </ForEach>'
        )
        issues = lint_xaml(xaml)
        h007 = [i for i in issues if i.rule_id == "XL-H007"]
        assert h007 == []

    def test_datatable_valid(self):
        xaml = _wrap(
            '    <ForEach TypeArgument="System.Data.DataRow" DisplayName="Loop">\n'
            '      <ForEach.Body>\n'
            '        <ActivityAction>\n'
            '          <Sequence DisplayName="Body" />\n'
            '        </ActivityAction>\n'
            '      </ForEach.Body>\n'
            '    </ForEach>'
        )
        issues = lint_xaml(xaml)
        h007 = [i for i in issues if i.rule_id == "XL-H007"]
        assert h007 == []


# ===================================================================
# XL-H008: Duplicate DisplayNames
# ===================================================================

class TestDuplicateDisplayNames:

    def test_duplicate_display_names_flagged(self):
        xaml = _wrap(
            '    <ui:LogMessage DisplayName="Log Step" Level="Info" Message="a" />\n'
            '    <ui:LogMessage DisplayName="Log Step" Level="Info" Message="b" />'
        )
        issues = lint_xaml(xaml)
        h008 = [i for i in issues if i.rule_id == "XL-H008"]
        assert len(h008) >= 1
        assert any("Log Step" in i.message for i in h008)

    def test_unique_display_names_not_flagged(self):
        xaml = _wrap(
            '    <ui:LogMessage DisplayName="Log A" Level="Info" Message="a" />\n'
            '    <ui:LogMessage DisplayName="Log B" Level="Info" Message="b" />'
        )
        issues = lint_xaml(xaml)
        h008 = [i for i in issues if i.rule_id == "XL-H008"]
        assert h008 == []


# ===================================================================
# XL-S002: Credential arguments
# ===================================================================

class TestCredentialArguments:

    def test_credential_in_arg_without_get_robot_credential(self):
        xaml = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<Activity\n'
            '  xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"\n'
            '  xmlns:ui="http://schemas.uipath.com/workflow/activities"\n'
            '  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"\n'
            '  x:Class="Login">\n'
            '  <x:Members>\n'
            '    <x:Property Name="in_Password" Type="InArgument(x:String)" />\n'
            '  </x:Members>\n'
            '  <Sequence DisplayName="Main">\n'
            '    <ui:LogMessage Level="Info" Message="login" DisplayName="Log" />\n'
            '  </Sequence>\n'
            '</Activity>\n'
        )
        issues = lint_xaml(xaml)
        s002 = [i for i in issues if i.rule_id == "XL-S002"]
        assert len(s002) >= 1
        assert any("Password" in i.message for i in s002)

    def test_credential_with_get_robot_credential_not_flagged(self):
        xaml = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<Activity\n'
            '  xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"\n'
            '  xmlns:ui="http://schemas.uipath.com/workflow/activities"\n'
            '  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"\n'
            '  x:Class="Login">\n'
            '  <x:Members>\n'
            '    <x:Property Name="in_Password" Type="InArgument(x:String)" />\n'
            '  </x:Members>\n'
            '  <Sequence DisplayName="Main">\n'
            '    <ui:GetRobotCredential AssetName="MyCredential" DisplayName="Get Cred" />\n'
            '  </Sequence>\n'
            '</Activity>\n'
        )
        issues = lint_xaml(xaml)
        s002 = [i for i in issues if i.rule_id == "XL-S002"]
        assert s002 == []


# ===================================================================
# XL-S003: Hardcoded secrets
# ===================================================================

class TestHardcodedSecrets:

    def test_hardcoded_api_key_in_attribute(self):
        xaml = _wrap(
            '    <Assign DisplayName="Set Key">\n'
            '      <Assign.To>\n'
            '        <OutArgument x:TypeArguments="x:String">[key]</OutArgument>\n'
            '      </Assign.To>\n'
            '      <Assign.Value>\n'
            '        <InArgument x:TypeArguments="x:String"'
            ' apikey="AKIA1234567890ABCDEF">val</InArgument>\n'
            '      </Assign.Value>\n'
            '    </Assign>'
        )
        issues = lint_xaml(xaml)
        s003 = [i for i in issues if i.rule_id == "XL-S003"]
        assert len(s003) >= 1

    def test_hardcoded_secret_in_password_attr(self):
        xaml = _wrap(
            '    <ui:NClick password="supersecretpassword12345678901234" DisplayName="Click" />'
        )
        issues = lint_xaml(xaml)
        s003 = [i for i in issues if i.rule_id == "XL-S003"]
        assert len(s003) >= 1


# ===================================================================
# XL-S004: Plaintext connection strings
# ===================================================================

class TestPlaintextConnectionStrings:

    def test_connection_string_with_password_flagged(self):
        xaml = _wrap(
            '    <Assign DisplayName="Set Conn">\n'
            '      <Assign.To>\n'
            '        <OutArgument x:TypeArguments="x:String">[conn]</OutArgument>\n'
            '      </Assign.To>\n'
            '      <Assign.Value>\n'
            '        <InArgument x:TypeArguments="x:String">'
            'Server=myserver;Database=mydb;Password=secret123'
            '</InArgument>\n'
            '      </Assign.Value>\n'
            '    </Assign>'
        )
        issues = lint_xaml(xaml)
        s004 = [i for i in issues if i.rule_id == "XL-S004"]
        assert len(s004) >= 1

    def test_connection_string_without_password_not_flagged(self):
        xaml = _wrap(
            '    <Assign DisplayName="Set Conn">\n'
            '      <Assign.To>\n'
            '        <OutArgument x:TypeArguments="x:String">[conn]</OutArgument>\n'
            '      </Assign.To>\n'
            '      <Assign.Value>\n'
            '        <InArgument x:TypeArguments="x:String">'
            'Server=myserver;Database=mydb;Integrated Security=True'
            '</InArgument>\n'
            '      </Assign.Value>\n'
            '    </Assign>'
        )
        issues = lint_xaml(xaml)
        s004 = [i for i in issues if i.rule_id == "XL-S004"]
        assert s004 == []


# ===================================================================
# XL-B002: Missing LogMessage
# ===================================================================

class TestMissingLogMessages:

    def test_no_log_message_flagged(self):
        xaml = _wrap(
            '    <Assign DisplayName="Set Var">\n'
            '      <Assign.To>\n'
            '        <OutArgument x:TypeArguments="x:String">[x]</OutArgument>\n'
            '      </Assign.To>\n'
            '      <Assign.Value>\n'
            '        <InArgument x:TypeArguments="x:String">"hello"</InArgument>\n'
            '      </Assign.Value>\n'
            '    </Assign>'
        )
        issues = lint_xaml(xaml)
        b002 = [i for i in issues if i.rule_id == "XL-B002"]
        assert len(b002) >= 1

    def test_with_log_message_not_flagged(self):
        xaml = _wrap(
            '    <ui:LogMessage DisplayName="Log" Level="Info" Message="ok" />'
        )
        issues = lint_xaml(xaml)
        b002 = [i for i in issues if i.rule_id == "XL-B002"]
        assert b002 == []


# ===================================================================
# XL-B003: Missing RetryScope around API calls
# ===================================================================

class TestMissingRetryScope:

    def test_http_client_without_retry_flagged(self):
        xaml = _wrap(
            '    <HttpClient DisplayName="Call API" />'
        )
        issues = lint_xaml(xaml)
        b003 = [i for i in issues if i.rule_id == "XL-B003"]
        assert len(b003) >= 1

    def test_http_client_inside_retry_scope_not_flagged(self):
        xaml = _wrap(
            '    <RetryScope DisplayName="Retry">\n'
            '      <RetryScope.Body>\n'
            '        <HttpClient DisplayName="Call API" />\n'
            '      </RetryScope.Body>\n'
            '    </RetryScope>'
        )
        issues = lint_xaml(xaml)
        b003 = [i for i in issues if i.rule_id == "XL-B003"]
        assert b003 == []


# ===================================================================
# XL-B004: Missing top-level TryCatch
# ===================================================================

class TestMissingTryCatch:

    def test_no_try_catch_flagged(self):
        xaml = _wrap(
            '    <ui:LogMessage DisplayName="Log" Level="Info" Message="hi" />'
        )
        issues = lint_xaml(xaml)
        b004 = [i for i in issues if i.rule_id == "XL-B004"]
        assert len(b004) >= 1

    def test_with_try_catch_not_flagged(self):
        xaml = _wrap(
            '    <TryCatch DisplayName="Main Try">\n'
            '      <TryCatch.Try>\n'
            '        <ui:LogMessage DisplayName="Log" Level="Info" Message="hi" />\n'
            '      </TryCatch.Try>\n'
            '      <TryCatch.Catches>\n'
            '        <Catch TypeArgument="s:Exception" />\n'
            '      </TryCatch.Catches>\n'
            '    </TryCatch>'
        )
        issues = lint_xaml(xaml)
        b004 = [i for i in issues if i.rule_id == "XL-B004"]
        assert b004 == []


# ===================================================================
# XL-B005: C# syntax in VB.NET context
# ===================================================================

class TestCSharpInVbNet:

    def test_csharp_null_in_vb_flagged(self):
        xaml = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<Activity\n'
            '  xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"\n'
            '  xmlns:ui="http://schemas.uipath.com/workflow/activities"\n'
            '  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">\n'
            '  <TextExpression.ReferencesForImplementation>\n'
            '    <VisualBasicSettings />\n'
            '  </TextExpression.ReferencesForImplementation>\n'
            '  <Sequence DisplayName="Main">\n'
            '    <If Condition="result != null" DisplayName="Check">\n'
            '      <If.Then>\n'
            '        <Assign DisplayName="Set">\n'
            '          <Assign.To>\n'
            '            <OutArgument x:TypeArguments="x:String">[x]</OutArgument>\n'
            '          </Assign.To>\n'
            '          <Assign.Value>\n'
            '            <InArgument x:TypeArguments="x:String">"ok"</InArgument>\n'
            '          </Assign.Value>\n'
            '        </Assign>\n'
            '      </If.Then>\n'
            '    </If>\n'
            '  </Sequence>\n'
            '</Activity>\n'
        )
        issues = lint_xaml(xaml)
        b005 = [i for i in issues if i.rule_id == "XL-B005"]
        assert len(b005) >= 1

    def test_csharp_project_not_flagged(self):
        """C# projects should not be flagged for C# syntax."""
        xaml = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<Activity\n'
            '  xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"\n'
            '  xmlns:ui="http://schemas.uipath.com/workflow/activities"\n'
            '  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">\n'
            '  <Sequence DisplayName="Main">\n'
            '    <CSharpValue />\n'
            '    <If Condition="result != null" DisplayName="Check">\n'
            '      <If.Then>\n'
            '        <Assign DisplayName="Set">\n'
            '          <Assign.To>\n'
            '            <OutArgument x:TypeArguments="x:String">[x]</OutArgument>\n'
            '          </Assign.To>\n'
            '          <Assign.Value>\n'
            '            <InArgument x:TypeArguments="x:String">"ok"</InArgument>\n'
            '          </Assign.Value>\n'
            '        </Assign>\n'
            '      </If.Then>\n'
            '    </If>\n'
            '  </Sequence>\n'
            '</Activity>\n'
        )
        issues = lint_xaml(xaml)
        b005 = [i for i in issues if i.rule_id == "XL-B005"]
        assert b005 == []


# ===================================================================
# XL-B006: Placeholder selectors
# ===================================================================

class TestPlaceholderSelectors:

    def test_todo_in_selector_flagged(self):
        xaml = _wrap(
            '    <ui:NClick DisplayName="Click" Selector="&lt;html TODO /&gt;" />'
        )
        issues = lint_xaml(xaml)
        b006 = [i for i in issues if i.rule_id == "XL-B006"]
        assert len(b006) >= 1

    def test_mustache_placeholder_flagged(self):
        xaml = _wrap(
            '    <ui:NClick DisplayName="Click" Selector="&lt;html id={{element_id}} /&gt;" />'
        )
        issues = lint_xaml(xaml)
        b006 = [i for i in issues if i.rule_id == "XL-B006"]
        assert len(b006) >= 1


# ===================================================================
# XL-B007: Empty catch blocks
# ===================================================================

class TestEmptyCatchBlocks:

    def test_empty_catch_flagged(self):
        xaml = _wrap(
            '    <TryCatch DisplayName="Try">\n'
            '      <TryCatch.Try>\n'
            '        <ui:LogMessage DisplayName="Log" Level="Info" Message="try" />\n'
            '      </TryCatch.Try>\n'
            '      <TryCatch.Catches>\n'
            '        <Catch TypeArgument="s:Exception">\n'
            '          <ActivityAction>\n'
            '            <Sequence DisplayName="Empty Catch" />\n'
            '          </ActivityAction>\n'
            '        </Catch>\n'
            '      </TryCatch.Catches>\n'
            '    </TryCatch>'
        )
        issues = lint_xaml(xaml)
        b007 = [i for i in issues if i.rule_id == "XL-B007"]
        assert len(b007) >= 1

    def test_non_empty_catch_not_flagged(self):
        xaml = _wrap(
            '    <TryCatch DisplayName="Try">\n'
            '      <TryCatch.Try>\n'
            '        <ui:LogMessage DisplayName="Log" Level="Info" Message="try" />\n'
            '      </TryCatch.Try>\n'
            '      <TryCatch.Catches>\n'
            '        <Catch TypeArgument="s:Exception">\n'
            '          <ActivityAction>\n'
            '            <Sequence DisplayName="Handle Error">\n'
            '              <ui:LogMessage DisplayName="Log Error" Level="Error" Message="fail" />\n'
            '            </Sequence>\n'
            '          </ActivityAction>\n'
            '        </Catch>\n'
            '      </TryCatch.Catches>\n'
            '    </TryCatch>'
        )
        issues = lint_xaml(xaml)
        b007 = [i for i in issues if i.rule_id == "XL-B007"]
        assert b007 == []


# ===================================================================
# XL-B008: Magic delay numbers
# ===================================================================

class TestMagicNumbers:

    def test_hardcoded_delay_flagged(self):
        xaml = _wrap(
            '    <Delay Duration="00:00:05" DisplayName="Wait" />'
        )
        issues = lint_xaml(xaml)
        b008 = [i for i in issues if i.rule_id == "XL-B008"]
        assert len(b008) >= 1

    def test_hardcoded_timeout_flagged(self):
        xaml = _wrap(
            '    <ui:NClick DisplayName="Click" TimeoutMS="30000" />'
        )
        issues = lint_xaml(xaml)
        b008 = [i for i in issues if i.rule_id == "XL-B008"]
        assert len(b008) >= 1

    def test_expression_delay_not_flagged(self):
        xaml = _wrap(
            '    <Delay Duration="[configTimeout]" DisplayName="Wait" />'
        )
        issues = lint_xaml(xaml)
        b008 = [i for i in issues if i.rule_id == "XL-B008"]
        assert b008 == []
