"""End-to-end: lifecycle graph wires the fix_node + registry correctly."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from rpa_architect.lifecycle.agent import create_lifecycle_graph


def test_graph_builds_without_swarm() -> None:
    """Backwards compatibility — no fix branch, original topology."""
    graph = create_lifecycle_graph()
    assert graph is not None


def test_graph_builds_with_swarm(tmp_path: Path) -> None:
    """Legacy entrypoint: passing a SwarmOrchestrator wraps it in the registry."""
    from rpa_architect.lifecycle.state import FailureBundle
    from rpa_architect.lifecycle.swarm.graph import SwarmOrchestrator

    class _Stub:
        async def fetch(self, job_id: str) -> FailureBundle:
            raise NotImplementedError

        async def validate(self, bundle, candidate):
            raise NotImplementedError

        def open(self, **kwargs):
            raise NotImplementedError

    stub = _Stub()
    orchestrator = SwarmOrchestrator(
        fetcher=stub,
        specialists=[],
        staging_validator=stub,
        pr_opener=stub,
        repo_root=tmp_path,
        base_branch="main",
        target_url=None,
    )
    graph = create_lifecycle_graph(swarm=orchestrator)
    assert graph is not None


def test_swarm_and_registry_are_mutually_exclusive(tmp_path: Path) -> None:
    """Passing both `swarm` and `fixer_registry` is rejected to keep wiring deterministic."""
    from rpa_architect.lifecycle.fault_fixer import FixerRegistry
    from rpa_architect.lifecycle.swarm.graph import SwarmOrchestrator

    class _Stub:
        async def fetch(self, job_id):
            raise NotImplementedError

        async def validate(self, bundle, candidate):
            raise NotImplementedError

        def open(self, **kwargs):
            raise NotImplementedError

    stub = _Stub()
    orchestrator = SwarmOrchestrator(
        fetcher=stub,
        specialists=[],
        staging_validator=stub,
        pr_opener=stub,
        repo_root=tmp_path,
        base_branch="main",
        target_url=None,
    )

    with pytest.raises(ValueError, match="not both"):
        create_lifecycle_graph(swarm=orchestrator, fixer_registry=FixerRegistry([]), fetcher=stub)


def test_registry_without_fetcher_is_accepted() -> None:
    """fetcher is optional now — fix_node synthesizes a lean bundle from state."""
    from rpa_architect.lifecycle.fault_fixer import FixerRegistry

    graph = create_lifecycle_graph(fixer_registry=FixerRegistry([]))
    assert graph is not None


@pytest.mark.asyncio
async def test_fix_node_runs_with_faulted_job_and_populates_outcome(tmp_path: Path) -> None:
    """End-to-end: a faulted job → registry → SwarmFaultFixer wins → PR url on state."""
    from rpa_architect.lifecycle.fault_fixer import FixerRegistry
    from rpa_architect.lifecycle.fix_node import build_fix_node
    from rpa_architect.lifecycle.state import (
        ExecutionLog,
        FailureBundle,
        FixCandidate,
        LifecycleRequest,
        LifecycleState,
        MonitoringOutputs,
        MonitoringReport,
        StagingResult,
        XamlPatch,
    )
    from rpa_architect.lifecycle.swarm.graph import SwarmOrchestrator
    from rpa_architect.lifecycle.swarm.pr_opener import PROpenResult
    from rpa_architect.lifecycle.swarm_fault_fixer import SwarmFaultFixer

    class _Fetcher:
        async def fetch(self, job_id: str) -> FailureBundle:
            return FailureBundle(
                job_id=job_id,
                process_key="Invoice",
                state="Faulted",
                exception_message="boom",
                exception_type="SelectorNotFoundException",
                xaml_files={"Main.xaml": "<x/>"},
            )

    class _Specialist:
        name = "selector_repair"

        async def propose(self, bundle, xaml_docs, *, target_url):
            return FixCandidate(
                specialist=self.name,
                confidence=0.8,
                diagnosis_category="selector_drift",
                patches=[
                    XamlPatch(
                        file_path="Main.xaml",
                        target_xpath="/x",
                        attribute="Selector",
                        old_value="a",
                        new_value="b",
                    )
                ],
                patched_xaml={"Main.xaml": "<x/>"},
            )

    class _Stager:
        async def validate(self, bundle, candidate):
            return StagingResult(
                candidate_specialist=candidate.specialist,
                success=True,
                job_id="s1",
            )

    class _Opener:
        def open(self, **kwargs):
            return PROpenResult(pr_url="https://github.com/o/r/pull/1", branch="b", commit_sha="c")

    orchestrator = SwarmOrchestrator(
        fetcher=_Fetcher(),
        specialists=[_Specialist()],
        staging_validator=_Stager(),
        pr_opener=_Opener(),
        repo_root=tmp_path,
        base_branch="main",
        target_url="https://app",
    )
    registry = FixerRegistry([SwarmFaultFixer(orchestrator=orchestrator)])
    node = build_fix_node(registry=registry, fetcher=_Fetcher())

    state = LifecycleState(
        request=LifecycleRequest(source="pdd-text", source_type="natural_language"),
        monitoring=MonitoringOutputs(
            report=MonitoringReport(
                process_key="Invoice",
                period_start=datetime(2026, 4, 20, tzinfo=timezone.utc),
                period_end=datetime(2026, 4, 20, tzinfo=timezone.utc),
                faulted=1,
                failed_jobs=[
                    ExecutionLog(
                        job_id="j-prod-1",
                        state="Faulted",
                        started_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
                    )
                ],
            )
        ),
    )
    out = await node(state)

    # New unified fields
    assert out.fix.outcome is not None
    assert out.fix.outcome.fixer == "swarm"
    assert out.fix.outcome.delivery_url == "https://github.com/o/r/pull/1"
    assert out.fix.outcome.requires_escalation is False
    assert len(out.fix.history) == 1
    # History event recorded
    assert any(h.event_type == "fix_remediate" for h in out.history)
