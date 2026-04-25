"""Contract tests for SwarmFaultFixer adapter.

Verifies the SwarmVerdict → FixOutcome mapping and the can_handle gate.
The orchestrator is faked so these tests run without Playwright / git / lxml.
"""

from __future__ import annotations

import pytest

from rpa_architect.lifecycle.fault_fixer import FaultFixer, FixOutcome
from rpa_architect.lifecycle.state import (
    FailureBundle,
    FixCandidate,
    StagingResult,
    XamlPatch,
)
from rpa_architect.lifecycle.swarm.arbiter import ArbiterVerdict
from rpa_architect.lifecycle.swarm.graph import SwarmVerdict
from rpa_architect.lifecycle.swarm_fault_fixer import SwarmFaultFixer


def _bundle(
    *, with_xaml: bool = True, exception_type: str = "SelectorNotFoundException"
) -> FailureBundle:
    return FailureBundle(
        job_id="job-42",
        process_key="ProcessInvoice",
        state="Faulted",
        exception_message="boom",
        exception_type=exception_type,
        xaml_files={"Main.xaml": "<Activity/>"} if with_xaml else {},
    )


def _winner_candidate() -> FixCandidate:
    return FixCandidate(
        specialist="selector_repair",
        confidence=0.83,
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
    )


class _FakeOrchestrator:
    """Test double matching SwarmHealer protocol — records calls + returns scripted verdict."""

    def __init__(self, verdict: SwarmVerdict) -> None:
        self._verdict = verdict
        self.heal_bundle_calls: list[FailureBundle] = []

    async def heal_bundle(self, bundle: FailureBundle) -> SwarmVerdict:
        self.heal_bundle_calls.append(bundle)
        return self._verdict


def _verdict(
    *,
    winner: FixCandidate | None,
    pr_url: str,
    requires_escalation: bool,
    staging_success: bool = True,
    candidates: list[FixCandidate] | None = None,
) -> SwarmVerdict:
    return SwarmVerdict(
        bundle=_bundle(),
        arbiter_verdict=ArbiterVerdict(
            winner=winner,
            considered=candidates or ([winner] if winner else []),
            requires_escalation=requires_escalation,
            rationale="test",
        ),
        staging=StagingResult(
            candidate_specialist=winner.specialist if winner else "",
            success=staging_success,
            job_id="staging-1",
            message="ok" if staging_success else "fail",
            release_key="rel",
        )
        if winner
        else None,
        staging_success=staging_success,
        pr_url=pr_url,
        requires_escalation=requires_escalation,
        candidates=candidates or ([winner] if winner else []),
    )


class TestCanHandle:
    @pytest.mark.asyncio
    async def test_claims_when_xaml_files_present(self) -> None:
        fixer = SwarmFaultFixer(
            orchestrator=_FakeOrchestrator(
                _verdict(winner=None, pr_url="", requires_escalation=True)
            )
        )
        assert await fixer.can_handle(_bundle(with_xaml=True)) is True

    @pytest.mark.asyncio
    async def test_declines_when_no_xaml_files(self) -> None:
        fixer = SwarmFaultFixer(
            orchestrator=_FakeOrchestrator(
                _verdict(winner=None, pr_url="", requires_escalation=True)
            )
        )
        assert await fixer.can_handle(_bundle(with_xaml=False)) is False


class TestFix:
    @pytest.mark.asyncio
    async def test_pr_opened_maps_to_success(self) -> None:
        winner = _winner_candidate()
        orch = _FakeOrchestrator(
            _verdict(
                winner=winner,
                pr_url="https://github.com/org/repo/pull/9",
                requires_escalation=False,
                staging_success=True,
            )
        )
        fixer = SwarmFaultFixer(orchestrator=orch)

        outcome = await fixer.fix(_bundle())

        assert outcome.fixer == "swarm"
        assert outcome.success is True
        assert outcome.requires_escalation is False
        assert outcome.delivery_url == "https://github.com/org/repo/pull/9"
        assert outcome.diagnosis_category == "selector_drift"
        # Adapter passes the same bundle through — no double-fetch.
        assert len(orch.heal_bundle_calls) == 1

    @pytest.mark.asyncio
    async def test_escalation_maps_to_failure_with_escalation(self) -> None:
        orch = _FakeOrchestrator(_verdict(winner=None, pr_url="", requires_escalation=True))
        fixer = SwarmFaultFixer(orchestrator=orch)

        outcome = await fixer.fix(_bundle())

        assert outcome.fixer == "swarm"
        assert outcome.success is False
        assert outcome.requires_escalation is True
        assert outcome.delivery_url == ""

    @pytest.mark.asyncio
    async def test_winner_without_pr_is_failure(self) -> None:
        # Edge case: arbiter chose a diagnostic winner with no patches → no PR, escalation.
        winner = FixCandidate(
            specialist="null_exception",
            confidence=0.5,
            diagnosis_category="code_bug",
            patches=[],
        )
        orch = _FakeOrchestrator(
            _verdict(winner=winner, pr_url="", requires_escalation=True, staging_success=False)
        )
        fixer = SwarmFaultFixer(orchestrator=orch)

        outcome = await fixer.fix(_bundle())

        assert outcome.success is False
        assert outcome.requires_escalation is True
        assert outcome.diagnosis_category == "code_bug"

    @pytest.mark.asyncio
    async def test_no_winner_diagnosis_category_falls_back_to_unknown(self) -> None:
        orch = _FakeOrchestrator(_verdict(winner=None, pr_url="", requires_escalation=True))
        fixer = SwarmFaultFixer(orchestrator=orch)

        outcome = await fixer.fix(_bundle())

        assert outcome.diagnosis_category == "unknown"

    @pytest.mark.asyncio
    async def test_evidence_carries_swarm_specifics(self) -> None:
        winner = _winner_candidate()
        candidates = [
            winner,
            FixCandidate(
                specialist="timing_repair", confidence=0.4, diagnosis_category="system_timeout"
            ),
        ]
        orch = _FakeOrchestrator(
            _verdict(
                winner=winner,
                pr_url="https://github.com/org/repo/pull/9",
                requires_escalation=False,
                candidates=candidates,
            )
        )
        fixer = SwarmFaultFixer(orchestrator=orch)

        outcome = await fixer.fix(_bundle())

        assert outcome.evidence["specialist"] == "selector_repair"
        assert outcome.evidence["confidence"] == 0.83
        assert outcome.evidence["candidate_count"] == 2
        assert outcome.evidence["staging_success"] is True
        assert "rationale" in outcome.evidence


class TestProtocolConformance:
    def test_satisfies_fault_fixer_protocol(self) -> None:
        fixer: FaultFixer = SwarmFaultFixer(
            orchestrator=_FakeOrchestrator(
                _verdict(winner=None, pr_url="", requires_escalation=True)
            )
        )
        assert fixer.name == "swarm"

    @pytest.mark.asyncio
    async def test_returns_fix_outcome_instance(self) -> None:
        fixer = SwarmFaultFixer(
            orchestrator=_FakeOrchestrator(
                _verdict(winner=None, pr_url="", requires_escalation=True)
            )
        )
        outcome = await fixer.fix(_bundle())
        assert isinstance(outcome, FixOutcome)
