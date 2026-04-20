"""ir_lifter: lift a REFramework XAML bundle into ProcessIR.

Scope: REFramework dispatcher pattern only. Non-REFramework XAML raises
UnsupportedPatternError with a helpful message.
"""

from __future__ import annotations

import pytest

from rpa_architect.ir.schema import ProcessIR, Transaction
from rpa_architect.migrator.ir_lifter import (
    UnsupportedPatternError,
    lift_xaml_bundle,
)


# Minimal REFramework shape. The lifter looks for the four canonical states.
REFRAMEWORK_MAIN = """<?xml version="1.0"?>
<Activity xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
          xmlns:ui="http://schemas.uipath.com/workflow/activities"
          xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <StateMachine DisplayName="InvoiceProcessing Main">
    <State x:Name="State_Init" DisplayName="Init"/>
    <State x:Name="State_GetTransactionData" DisplayName="Get Transaction Data"/>
    <State x:Name="State_ProcessTransaction" DisplayName="Process Transaction">
      <State.Entry>
        <Sequence>
          <ui:InvokeWorkflowFile FilePath="Process.xaml"/>
        </Sequence>
      </State.Entry>
    </State>
    <State x:Name="State_EndProcess" DisplayName="End Process" IsFinal="True"/>
  </StateMachine>
</Activity>
"""

PROCESS_XAML = """<?xml version="1.0"?>
<Activity xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
          xmlns:ui="http://schemas.uipath.com/workflow/activities"
          xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName="Process Invoice">
    <ui:LogMessage DisplayName="Log Start" Level="Info" Message="start"/>
    <ui:TypeInto DisplayName="Type Invoice Number" Text="{{invoice_number}}">
      <ui:TypeInto.Target>
        <ui:Target Selector="&lt;webctrl id='invoice-num' /&gt;"/>
      </ui:TypeInto.Target>
    </ui:TypeInto>
    <ui:Click DisplayName="Click Submit">
      <ui:Click.Target>
        <ui:Target Selector="&lt;webctrl id='submit' /&gt;"/>
      </ui:Click.Target>
    </ui:Click>
    <ui:GetText DisplayName="Get Confirmation">
      <ui:GetText.Target>
        <ui:Target Selector="&lt;webctrl id='confirmation' /&gt;"/>
      </ui:GetText.Target>
    </ui:GetText>
    <ui:LogMessage DisplayName="Log Done" Level="Info" Message="done"/>
  </Sequence>
</Activity>
"""


class TestLiftXamlBundle:
    def test_returns_process_ir(self) -> None:
        ir = lift_xaml_bundle({"Main.xaml": REFRAMEWORK_MAIN, "Process.xaml": PROCESS_XAML})
        assert isinstance(ir, ProcessIR)
        assert ir.process_name == "InvoiceProcessing"

    def test_creates_one_transaction(self) -> None:
        ir = lift_xaml_bundle({"Main.xaml": REFRAMEWORK_MAIN, "Process.xaml": PROCESS_XAML})
        assert len(ir.transactions) == 1
        tx = ir.transactions[0]
        assert isinstance(tx, Transaction)

    def test_lifts_process_ui_actions(self) -> None:
        ir = lift_xaml_bundle({"Main.xaml": REFRAMEWORK_MAIN, "Process.xaml": PROCESS_XAML})
        tx = ir.transactions[0]
        actions = [a for step in tx.steps for a in step.actions]
        # 3 UI actions: TypeInto, Click, GetText (LogMessage is not UI)
        ui_actions = [a for a in actions if a.action in ("type_into", "click", "get_text")]
        assert len(ui_actions) == 3

    def test_preserves_selector_hints(self) -> None:
        ir = lift_xaml_bundle({"Main.xaml": REFRAMEWORK_MAIN, "Process.xaml": PROCESS_XAML})
        tx = ir.transactions[0]
        all_selectors = [
            a.selector_hint for step in tx.steps for a in step.actions if a.selector_hint
        ]
        joined = " ".join(all_selectors)
        assert "invoice-num" in joined
        assert "submit" in joined
        assert "confirmation" in joined

    def test_preserves_target_display_name(self) -> None:
        ir = lift_xaml_bundle({"Main.xaml": REFRAMEWORK_MAIN, "Process.xaml": PROCESS_XAML})
        tx = ir.transactions[0]
        targets = [a.target for step in tx.steps for a in step.actions]
        assert "Click Submit" in targets
        assert "Type Invoice Number" in targets


class TestUnsupportedPatterns:
    def test_rejects_non_reframework(self) -> None:
        plain = """<?xml version="1.0"?>
<Activity xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
          xmlns:ui="http://schemas.uipath.com/workflow/activities">
  <Sequence>
    <ui:LogMessage DisplayName="Log" Level="Info" Message="hi"/>
  </Sequence>
</Activity>
"""
        with pytest.raises(UnsupportedPatternError, match="REFramework"):
            lift_xaml_bundle({"Main.xaml": plain})

    def test_rejects_missing_process_xaml(self) -> None:
        with pytest.raises(UnsupportedPatternError, match="Process.xaml"):
            lift_xaml_bundle({"Main.xaml": REFRAMEWORK_MAIN})

    def test_empty_bundle_raises(self) -> None:
        with pytest.raises(UnsupportedPatternError):
            lift_xaml_bundle({})


class TestActionMapping:
    def test_unknown_activity_is_ignored(self) -> None:
        process = """<?xml version="1.0"?>
<Activity xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
          xmlns:ui="http://schemas.uipath.com/workflow/activities">
  <Sequence>
    <ui:SomeMadeUpActivity DisplayName="Thing"/>
    <ui:Click DisplayName="Real Click">
      <ui:Click.Target>
        <ui:Target Selector="&lt;webctrl id='x' /&gt;"/>
      </ui:Click.Target>
    </ui:Click>
  </Sequence>
</Activity>
"""
        ir = lift_xaml_bundle({"Main.xaml": REFRAMEWORK_MAIN, "Process.xaml": process})
        actions = [a for step in ir.transactions[0].steps for a in step.actions]
        # Only the Click is recognized; SomeMadeUpActivity is silently dropped.
        assert len(actions) == 1
        assert actions[0].action == "click"
