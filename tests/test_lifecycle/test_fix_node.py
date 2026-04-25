"""Tests for the unified fix_node — driven by FixerRegistry, replaces swarm_heal."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rpa_architect.lifecycle.fault_fixer import FixOutcome, FixerRegistry
from rpa_architect.lifecycle.fix_node import build_fix_node, route_after_fix
from rpa_architect.lifecycle.state import (
    ExecutionLog,
    FailureBundle,
    LifecyclePhase,
    LifecycleRequest,
    LifecycleState,
    MonitoringReport,
)


def _state(*, with_failed_job: bool = True) -> LifecycleState:
    s = LifecycleState(request=LifecycleRequest(source="x", source_type="pdd"))
    if with_failed_job:
        now = datetime(2026, 4, 25, tzinfo=timezone.utc)
        s.monitoring.report = MonitoringReport(
            process_key="P",
            period_start=now,
            period_end=now,
            total_jobs=1,
            successful=0,
            faulted=1,
            failed_jobs=[
                ExecutionLog(
                    job_id="job-1",
                    state="Faulted",
                    started_at=now,
                    info="boom",
                )
            ],
        )
    return s


class _ScriptedFetcher:
    def __init__(
        self, bundle: FailureBundle | None = None, raises: Exception | None = None
    ) -> None:
        self._bundle = bundle or FailureBundle(
            job_id="job-1",
            process_key="P",
            state="Faulted",
            exception_type="SelectorNotFoundException",
            xaml_files={"Main.xaml": "<Activity/>"},
        )
        self._raises = raises
        self.calls: list[str] = []

    async def fetch(self, job_id: str) -> FailureBundle:
        self.calls.append(job_id)
        if self._raises:
            raise self._raises
        return self._bundle


class _ScriptedFixer:
    def __init__(self, name: str, *, claims: bool, outcome: FixOutcome | None = None) -> None:
        self.name = name
        self._claims = claims
        self._outcome = outcome or FixOutcome(fixer=name, success=True, requires_escalation=False)

    async def can_handle(self, failure: FailureBundle) -> bool:
        return self._claims

    async def fix(self, failure: FailureBundle) -> FixOutcome:
        return self._outcome


class TestBuildFixNode:
    @pytest.mark.asyncio
    async def test_fetches_bundle_from_first_failed_job(self) -> None:
        fetcher = _ScriptedFetcher()
        registry = FixerRegistry([_ScriptedFixer("x", claims=True)])
        node = build_fix_node(registry=registry, fetcher=fetcher)

        await node(_state())

        assert fetcher.calls == ["job-1"]

    @pytest.mark.asyncio
    async def test_populates_last_fix_outcome(self) -> None:
        scripted = FixOutcome(
            fixer="swarm",
            success=True,
            requires_escalation=False,
            delivery_url="https://github.com/o/r/pull/9",
            diagnosis_category="selector_drift",
        )
        node = build_fix_node(
            registry=FixerRegistry([_ScriptedFixer("swarm", claims=True, outcome=scripted)]),
            fetcher=_ScriptedFetcher(),
        )

        result = await node(_state())

        assert result.fix.outcome is scripted
        assert result.fix.history == [scripted]

    @pytest.mark.asyncio
    async def test_appends_to_fix_history_across_runs(self) -> None:
        outcome_a = FixOutcome(fixer="a", success=True, requires_escalation=False)
        outcome_b = FixOutcome(fixer="b", success=False, requires_escalation=True)

        state = _state()
        # Pre-existing history (from a prior iteration)
        state.fix.history.append(outcome_a)

        node = build_fix_node(
            registry=FixerRegistry([_ScriptedFixer("b", claims=True, outcome=outcome_b)]),
            fetcher=_ScriptedFetcher(),
        )
        result = await node(state)

        assert len(result.fix.history) == 2
        assert result.fix.history[0] is outcome_a
        assert result.fix.history[1] is outcome_b
        assert result.fix.outcome is outcome_b

    @pytest.mark.asyncio
    async def test_no_failed_jobs_emits_escalation_outcome(self) -> None:
        node = build_fix_node(
            registry=FixerRegistry([_ScriptedFixer("x", claims=True)]),
            fetcher=_ScriptedFetcher(),
        )

        result = await node(_state(with_failed_job=False))

        assert result.fix.outcome is not None
        assert result.fix.outcome.requires_escalation is True
        assert result.fix.outcome.success is False
        assert "no faulted jobs" in result.fix.outcome.evidence["reason"]

    @pytest.mark.asyncio
    async def test_fetcher_exception_emits_escalation_outcome(self) -> None:
        node = build_fix_node(
            registry=FixerRegistry([_ScriptedFixer("x", claims=True)]),
            fetcher=_ScriptedFetcher(raises=RuntimeError("orchestrator down")),
        )

        result = await node(_state())

        assert result.fix.outcome is not None
        assert result.fix.outcome.success is False
        assert result.fix.outcome.requires_escalation is True
        assert "orchestrator down" in result.fix.outcome.evidence["error"]

    @pytest.mark.asyncio
    async def test_no_fetcher_synthesizes_bundle_from_state(self) -> None:
        """When no fetcher is wired, fix_node builds a lean bundle from state."""
        captured: list[FailureBundle] = []

        class _CapturingFixer:
            name = "capture"

            async def can_handle(self, failure: FailureBundle) -> bool:
                captured.append(failure)
                return True

            async def fix(self, failure: FailureBundle) -> FixOutcome:
                return FixOutcome(fixer=self.name, success=False, requires_escalation=True)

        node = build_fix_node(registry=FixerRegistry([_CapturingFixer()]))  # no fetcher

        # ExecutionLog.info shaped like "<Type>: <message>" → exception_type parsed.
        state = _state()
        state.monitoring.report.failed_jobs[0].info = "SelectorNotFoundException: lookup failed"
        await node(state)

        assert len(captured) == 1
        bundle = captured[0]
        assert bundle.job_id == "job-1"
        assert bundle.process_key == "P"
        assert bundle.state == "Faulted"
        assert bundle.exception_type == "SelectorNotFoundException"
        # No XAML when synthesized — swarm would correctly decline.
        assert bundle.xaml_files == {}

    @pytest.mark.asyncio
    async def test_no_fetcher_handles_unparseable_info(self) -> None:
        """If info doesn't have a clean type prefix, exception_type stays empty."""
        captured: list[FailureBundle] = []

        class _CapturingFixer:
            name = "c"

            async def can_handle(self, failure: FailureBundle) -> bool:
                captured.append(failure)
                return True

            async def fix(self, failure: FailureBundle) -> FixOutcome:
                return FixOutcome(fixer=self.name, success=False, requires_escalation=True)

        node = build_fix_node(registry=FixerRegistry([_CapturingFixer()]))
        state = _state()
        state.monitoring.report.failed_jobs[0].info = "weird unstructured error message"
        await node(state)

        assert captured[0].exception_type == ""

    @pytest.mark.asyncio
    async def test_no_proposal_double_generation(self, tmp_path) -> None:
        """Regression: fix_node + approval_gate + apply_fix read the SAME proposal,
        not two independently generated ones (the duplication bug from before).
        """
        from rpa_architect.lifecycle.fix_proposal_fixer import FixProposalFixer
        from rpa_architect.lifecycle.nodes import approval_gate_node

        # Real catch-all fixer; no fetcher (synthesizes bundle).
        registry = FixerRegistry([FixProposalFixer(project_dir=str(tmp_path))])
        node = build_fix_node(registry=registry)

        state = _state()
        state.monitoring.report.failed_jobs[0].info = "SelectorNotFoundException: gone"
        state.request.require_approval_for_fixes = False  # auto-approve

        # Run fix_node — proposal is generated ONCE and lives on outcome.
        await node(state)
        assert state.fix.outcome is not None
        proposal_from_fixer = state.fix.outcome.proposal
        assert proposal_from_fixer is not None
        proposal_id = proposal_from_fixer.proposal_id

        # Approval gate reads the SAME proposal — does not regenerate.
        await approval_gate_node(state)
        assert state.fix.outcome.proposal is proposal_from_fixer
        assert state.fix.outcome.proposal.proposal_id == proposal_id

    @pytest.mark.asyncio
    async def test_phase_transitions_to_diagnosing(self) -> None:
        node = build_fix_node(
            registry=FixerRegistry([_ScriptedFixer("x", claims=True)]),
            fetcher=_ScriptedFetcher(),
        )

        result = await node(_state())

        assert result.phase == LifecyclePhase.DIAGNOSING


class TestRouteAfterFix:
    def test_success_with_delivery_url_routes_to_end(self) -> None:
        from langgraph.graph import END

        state = _state()
        state.fix.outcome = FixOutcome(
            fixer="swarm",
            success=True,
            requires_escalation=False,
            delivery_url="https://pr/1",
        )
        assert route_after_fix(state) == END

    def test_escalation_routes_to_approval_gate(self) -> None:
        state = _state()
        state.fix.outcome = FixOutcome(
            fixer="swarm",
            success=False,
            requires_escalation=True,
        )
        assert route_after_fix(state) == "approval_gate"

    def test_no_outcome_routes_to_end(self) -> None:
        from langgraph.graph import END

        state = _state()
        state.fix.outcome = None
        assert route_after_fix(state) == END

    def test_no_action_no_escalation_routes_to_end(self) -> None:
        from langgraph.graph import END

        state = _state()
        state.fix.outcome = FixOutcome(
            fixer="swarm",
            success=False,
            requires_escalation=False,
        )
        assert route_after_fix(state) == END
