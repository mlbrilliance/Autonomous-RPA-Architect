"""Swarm sub-graph: parallel specialists, arbiter, staging, PR."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from rpa_architect.lifecycle.state import (
    FailureBundle,
    FixCandidate,
    StagingResult,
    XamlPatch,
)
from rpa_architect.lifecycle.swarm.graph import SwarmOrchestrator, SwarmVerdict


class FakeFetcher:
    def __init__(self, bundle: FailureBundle) -> None:
        self._bundle = bundle

    async def fetch(self, job_id: str) -> FailureBundle:
        return self._bundle


class FakeSpecialist:
    def __init__(self, name: str, candidate: FixCandidate | None) -> None:
        self.name = name
        self._candidate = candidate
        self.calls = 0

    async def propose(self, bundle, xaml_docs, *, target_url):
        self.calls += 1
        return self._candidate


class FakeStager:
    def __init__(self, success: bool = True) -> None:
        self._success = success
        self.calls = 0

    async def validate(self, bundle, candidate) -> StagingResult:
        self.calls += 1
        return StagingResult(
            candidate_specialist=candidate.specialist,
            success=self._success,
            job_id="staging-1",
            message="ok" if self._success else "staging failed",
            release_key="rel-staging",
        )


class FakePROpener:
    def __init__(self) -> None:
        self.calls = 0

    def open(self, *, bundle, candidate, base_branch, staging_url):
        self.calls += 1
        from rpa_architect.lifecycle.swarm.pr_opener import PROpenResult

        return PROpenResult(pr_url="https://github.com/org/repo/pull/7", branch="auto-heal/x", commit_sha="abc")


_SIMPLE_XAML = """<?xml version="1.0"?>
<Activity xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
          xmlns:ui="http://schemas.uipath.com/workflow/activities">
  <Sequence DisplayName="Main">
    <ui:Click DisplayName="Login">
      <ui:Click.Target>
        <ui:Target Selector="&lt;webctrl id='x' /&gt;" />
      </ui:Click.Target>
    </ui:Click>
  </Sequence>
</Activity>
"""


def _bundle() -> FailureBundle:
    return FailureBundle(
        job_id="j1",
        process_key="Invoice",
        state="Faulted",
        exception_message="SelectorNotFoundException: boom",
        exception_type="SelectorNotFoundException",
        started_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
        ended_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
        xaml_files={"Main.xaml": _SIMPLE_XAML},
    )


def _patching_candidate() -> FixCandidate:
    return FixCandidate(
        specialist="selector_repair",
        confidence=0.8,
        diagnosis_category="selector_drift",
        patches=[
            XamlPatch(
                file_path="Main.xaml",
                target_xpath="/a:Activity",
                attribute="Selector",
                old_value="<webctrl id='x'/>",
                new_value="<webctrl id='y'/>",
            )
        ],
        patched_xaml={"Main.xaml": "<Activity>patched</Activity>"},
    )


class TestSwarmOrchestrator:
    @pytest.mark.asyncio
    async def test_parallel_dispatch_to_all_specialists(self, tmp_path: Path) -> None:
        s1 = FakeSpecialist("s1", None)
        s2 = FakeSpecialist("s2", _patching_candidate())
        s3 = FakeSpecialist("s3", None)
        orch = SwarmOrchestrator(
            fetcher=FakeFetcher(_bundle()),
            specialists=[s1, s2, s3],
            staging_validator=FakeStager(success=True),
            pr_opener=FakePROpener(),
            repo_root=tmp_path,
            base_branch="main",
            target_url="https://app",
        )
        await orch.heal(job_id="j1")

        # Every specialist should have been invoked exactly once (parallel dispatch).
        assert s1.calls == 1
        assert s2.calls == 1
        assert s3.calls == 1

    @pytest.mark.asyncio
    async def test_successful_flow_opens_pr(self, tmp_path: Path) -> None:
        stager = FakeStager(success=True)
        opener = FakePROpener()
        orch = SwarmOrchestrator(
            fetcher=FakeFetcher(_bundle()),
            specialists=[FakeSpecialist("selector_repair", _patching_candidate())],
            staging_validator=stager,
            pr_opener=opener,
            repo_root=tmp_path,
            base_branch="main",
            target_url="https://app",
        )
        verdict = await orch.heal(job_id="j1")
        assert isinstance(verdict, SwarmVerdict)
        assert verdict.pr_url == "https://github.com/org/repo/pull/7"
        assert verdict.staging_success is True
        assert stager.calls == 1
        assert opener.calls == 1

    @pytest.mark.asyncio
    async def test_failed_staging_does_not_open_pr(self, tmp_path: Path) -> None:
        stager = FakeStager(success=False)
        opener = FakePROpener()
        orch = SwarmOrchestrator(
            fetcher=FakeFetcher(_bundle()),
            specialists=[FakeSpecialist("selector_repair", _patching_candidate())],
            staging_validator=stager,
            pr_opener=opener,
            repo_root=tmp_path,
            base_branch="main",
            target_url="https://app",
        )
        verdict = await orch.heal(job_id="j1")
        assert verdict.staging_success is False
        assert verdict.pr_url == ""
        assert opener.calls == 0
        assert verdict.requires_escalation is True

    @pytest.mark.asyncio
    async def test_escalation_when_no_patches(self, tmp_path: Path) -> None:
        """No specialist returns patches → PR is not opened, escalation flagged."""
        empty = FixCandidate(specialist="business_rule", confidence=0.9, diagnosis_category="business_rule_violation")
        opener = FakePROpener()
        orch = SwarmOrchestrator(
            fetcher=FakeFetcher(_bundle()),
            specialists=[FakeSpecialist("s", empty)],
            staging_validator=FakeStager(success=True),
            pr_opener=opener,
            repo_root=tmp_path,
            base_branch="main",
            target_url=None,
        )
        verdict = await orch.heal(job_id="j1")
        assert verdict.requires_escalation is True
        assert opener.calls == 0
