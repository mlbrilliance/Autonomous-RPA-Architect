"""Verify create_lifecycle_graph accepts an optional swarm and compiles."""

from __future__ import annotations

from pathlib import Path

import pytest

from rpa_architect.lifecycle.agent import create_lifecycle_graph


def test_graph_builds_without_swarm() -> None:
    """Backwards compatibility — no swarm, original topology."""
    graph = create_lifecycle_graph()
    assert graph is not None


def test_graph_builds_with_swarm(tmp_path: Path) -> None:
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
    # The graph should have a swarm_heal node.
    # LangGraph doesn't expose a clean API to list nodes, but compile() succeeded.


@pytest.mark.asyncio
async def test_swarm_node_runs_with_faulted_job(tmp_path: Path) -> None:
    """Swarm node should invoke heal and populate state.swarm_pr_url on success."""
    from datetime import datetime, timezone

    from rpa_architect.lifecycle.state import (
        ExecutionLog,
        FailureBundle,
        FixCandidate,
        LifecycleRequest,
        LifecycleState,
        MonitoringReport,
        StagingResult,
        XamlPatch,
    )
    from rpa_architect.lifecycle.swarm.graph import SwarmOrchestrator
    from rpa_architect.lifecycle.swarm.node import build_swarm_node
    from rpa_architect.lifecycle.swarm.pr_opener import PROpenResult

    class _Fetcher:
        async def fetch(self, job_id: str) -> FailureBundle:
            return FailureBundle(
                job_id=job_id,
                process_key="Invoice",
                state="Faulted",
                exception_message="boom",
                exception_type="SelectorNotFoundException",
                xaml_files={},
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
    node = build_swarm_node(orchestrator)
    state = LifecycleState(
        request=LifecycleRequest(source="pdd-text", source_type="natural_language"),
        monitoring_report=MonitoringReport(
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
        ),
    )
    out = await node(state)
    assert out.swarm_pr_url == "https://github.com/o/r/pull/1"
    assert out.swarm_requires_escalation is False
    assert any(h.event_type == "swarm_heal" for h in out.history)
