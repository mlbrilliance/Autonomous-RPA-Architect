"""Tests for the four swarm specialists.

Specialists take a FailureBundle + parsed XamlDocument and return a
FixCandidate — or None when the specialist has no opinion.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rpa_architect.lifecycle.state import FailureBundle, FixCandidate
from rpa_architect.lifecycle.swarm.specialists import (
    BusinessRuleSpecialist,
    NullExceptionSpecialist,
    TimingRepairSpecialist,
)
from rpa_architect.lifecycle.swarm.selector_repair import SelectorRepairSpecialist
from rpa_architect.xaml_ast import read_xaml


XAML_WITH_CLICK = """<?xml version="1.0"?>
<Activity xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
          xmlns:ui="http://schemas.uipath.com/workflow/activities"
          xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName="Main">
    <ui:Click DisplayName="Click Submit">
      <ui:Click.Target>
        <ui:Target Selector="&lt;webctrl id='submit' /&gt;" />
      </ui:Click.Target>
    </ui:Click>
  </Sequence>
</Activity>
"""


def _bundle(exception_type: str, message: str = "") -> FailureBundle:
    return FailureBundle(
        job_id="j",
        process_key="Invoice",
        state="Faulted",
        exception_message=message or f"{exception_type}: boom",
        exception_type=exception_type,
        started_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
        ended_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
        xaml_files={"Main.xaml": XAML_WITH_CLICK},
    )


class FakeHarvester:
    """Stand-in for browser_harvester — returns a canned new selector."""

    def __init__(self, new_selector: str = "<webctrl id='submit-v2' />") -> None:
        self._selector = new_selector

    async def harvest_replacement(
        self, *, url: str, activity_display_name: str
    ) -> str | None:
        return self._selector


class TestSelectorRepairSpecialist:
    @pytest.mark.asyncio
    async def test_fires_on_selector_not_found(self) -> None:
        specialist = SelectorRepairSpecialist(harvester=FakeHarvester())
        bundle = _bundle(
            "SelectorNotFoundException",
            "Could not find UI element matching <webctrl id='submit' /> (activity: Click Submit)",
        )
        doc = read_xaml(XAML_WITH_CLICK)
        candidate = await specialist.propose(bundle, {"Main.xaml": doc}, target_url="https://app")
        assert isinstance(candidate, FixCandidate)
        assert candidate.specialist == "selector_repair"
        assert candidate.confidence > 0.5
        assert candidate.diagnosis_category == "selector_drift"
        assert len(candidate.patches) == 1
        patch = candidate.patches[0]
        assert patch.old_value.startswith("<webctrl id='submit'")
        assert "submit-v2" in patch.new_value

    @pytest.mark.asyncio
    async def test_skips_on_non_selector_failure(self) -> None:
        specialist = SelectorRepairSpecialist(harvester=FakeHarvester())
        bundle = _bundle("NullReferenceException")
        doc = read_xaml(XAML_WITH_CLICK)
        candidate = await specialist.propose(bundle, {"Main.xaml": doc}, target_url="https://app")
        assert candidate is None

    @pytest.mark.asyncio
    async def test_skips_when_no_target_url(self) -> None:
        specialist = SelectorRepairSpecialist(harvester=FakeHarvester())
        bundle = _bundle("SelectorNotFoundException", "Could not find <webctrl id='submit' />")
        doc = read_xaml(XAML_WITH_CLICK)
        candidate = await specialist.propose(bundle, {"Main.xaml": doc}, target_url=None)
        # Without a URL, specialist should degrade to None rather than guess.
        assert candidate is None


class TestNullExceptionSpecialist:
    @pytest.mark.asyncio
    async def test_fires_on_null_reference(self) -> None:
        specialist = NullExceptionSpecialist()
        bundle = _bundle("NullReferenceException", "Object reference not set to an instance")
        doc = read_xaml(XAML_WITH_CLICK)
        candidate = await specialist.propose(bundle, {"Main.xaml": doc}, target_url=None)
        assert isinstance(candidate, FixCandidate)
        assert candidate.specialist == "null_exception"
        assert candidate.diagnosis_category == "code_bug"
        assert candidate.confidence > 0.4

    @pytest.mark.asyncio
    async def test_skips_on_selector_failure(self) -> None:
        specialist = NullExceptionSpecialist()
        bundle = _bundle("SelectorNotFoundException")
        doc = read_xaml(XAML_WITH_CLICK)
        candidate = await specialist.propose(bundle, {"Main.xaml": doc}, target_url=None)
        assert candidate is None


class TestTimingRepairSpecialist:
    @pytest.mark.asyncio
    async def test_fires_on_timeout(self) -> None:
        specialist = TimingRepairSpecialist()
        bundle = _bundle("TimeoutException", "UiElement not visible within 3s")
        doc = read_xaml(XAML_WITH_CLICK)
        candidate = await specialist.propose(bundle, {"Main.xaml": doc}, target_url=None)
        assert isinstance(candidate, FixCandidate)
        assert candidate.specialist == "timing_repair"
        assert candidate.diagnosis_category == "system_timeout"

    @pytest.mark.asyncio
    async def test_skips_on_null_reference(self) -> None:
        specialist = TimingRepairSpecialist()
        bundle = _bundle("NullReferenceException")
        doc = read_xaml(XAML_WITH_CLICK)
        candidate = await specialist.propose(bundle, {"Main.xaml": doc}, target_url=None)
        assert candidate is None


class TestBusinessRuleSpecialist:
    @pytest.mark.asyncio
    async def test_fires_on_business_rule_exception(self) -> None:
        specialist = BusinessRuleSpecialist()
        bundle = _bundle("BusinessRuleException", "Invoice amount exceeds limit")
        doc = read_xaml(XAML_WITH_CLICK)
        candidate = await specialist.propose(bundle, {"Main.xaml": doc}, target_url=None)
        assert isinstance(candidate, FixCandidate)
        assert candidate.specialist == "business_rule"
        assert candidate.diagnosis_category == "business_rule_violation"
        # Business rule specialist must NOT emit XAML patches — those decisions
        # belong to humans. It proposes zero patches with an escalation rationale.
        assert candidate.patches == []

    @pytest.mark.asyncio
    async def test_skips_on_non_business_rule(self) -> None:
        specialist = BusinessRuleSpecialist()
        bundle = _bundle("SelectorNotFoundException")
        doc = read_xaml(XAML_WITH_CLICK)
        candidate = await specialist.propose(bundle, {"Main.xaml": doc}, target_url=None)
        assert candidate is None
