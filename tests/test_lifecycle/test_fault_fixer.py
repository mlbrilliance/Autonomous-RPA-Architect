"""Contract tests for the FaultFixer Protocol and FixerRegistry."""

from __future__ import annotations

import pytest

from rpa_architect.lifecycle.fault_fixer import (
    FaultFixer,
    FixerRegistry,
    FixOutcome,
)
from rpa_architect.lifecycle.state import FailureBundle


def _bundle(exception_type: str = "SelectorNotFoundException") -> FailureBundle:
    return FailureBundle(
        job_id="job-1",
        process_key="ProcessInvoice",
        state="Faulted",
        exception_message="boom",
        exception_type=exception_type,
    )


class _RecordingFixer:
    """Test double — records calls and returns a scripted outcome."""

    def __init__(
        self,
        name: str,
        *,
        claims: bool,
        outcome: FixOutcome | None = None,
    ) -> None:
        self.name = name
        self._claims = claims
        self._outcome = outcome or FixOutcome(fixer=name, success=True, requires_escalation=False)
        self.can_handle_calls = 0
        self.fix_calls = 0

    async def can_handle(self, failure: FailureBundle) -> bool:
        self.can_handle_calls += 1
        return self._claims

    async def fix(self, failure: FailureBundle) -> FixOutcome:
        self.fix_calls += 1
        return self._outcome


class TestFixOutcome:
    def test_frozen_blocks_reassignment(self) -> None:
        outcome = FixOutcome(fixer="x", success=True, requires_escalation=False)
        with pytest.raises((AttributeError, Exception)):
            outcome.fixer = "y"  # type: ignore[misc]

    def test_evidence_default_is_per_instance(self) -> None:
        # field(default_factory=dict) → independent dicts per instance.
        a = FixOutcome(fixer="a", success=True, requires_escalation=False)
        b = FixOutcome(fixer="b", success=True, requires_escalation=False)
        a.evidence["key"] = "value"
        assert "key" not in b.evidence


class TestFixerRegistry:
    @pytest.mark.asyncio
    async def test_first_matching_fixer_wins(self) -> None:
        skip = _RecordingFixer("skip", claims=False)
        win = _RecordingFixer("win", claims=True)
        loser = _RecordingFixer("loser", claims=True)
        registry = FixerRegistry([skip, win, loser])

        outcome = await registry.remediate(_bundle())

        assert outcome.fixer == "win"
        assert skip.can_handle_calls == 1
        assert win.can_handle_calls == 1
        assert win.fix_calls == 1
        # Exclusive: loser is never consulted after a winner is found.
        assert loser.can_handle_calls == 0
        assert loser.fix_calls == 0

    @pytest.mark.asyncio
    async def test_no_fixer_claims_returns_escalation_outcome(self) -> None:
        a = _RecordingFixer("a", claims=False)
        b = _RecordingFixer("b", claims=False)
        registry = FixerRegistry([a, b])

        outcome = await registry.remediate(_bundle())

        assert outcome.fixer == "none"
        assert outcome.success is False
        assert outcome.requires_escalation is True
        assert "no fixer claimed" in outcome.evidence["reason"]
        assert a.fix_calls == 0
        assert b.fix_calls == 0

    @pytest.mark.asyncio
    async def test_empty_registry_returns_escalation_outcome(self) -> None:
        registry = FixerRegistry([])

        outcome = await registry.remediate(_bundle())

        assert outcome.fixer == "none"
        assert outcome.requires_escalation is True

    @pytest.mark.asyncio
    async def test_fixer_outcome_propagates_unchanged(self) -> None:
        scripted = FixOutcome(
            fixer="swarm",
            success=True,
            requires_escalation=False,
            delivery_url="https://github.com/org/repo/pull/42",
            diagnosis_category="selector_drift",
            evidence={"specialist": "selector_repair", "confidence": 0.78},
        )
        fixer = _RecordingFixer("swarm", claims=True, outcome=scripted)
        registry = FixerRegistry([fixer])

        outcome = await registry.remediate(_bundle())

        assert outcome is scripted

    def test_fixers_property_returns_copy(self) -> None:
        a = _RecordingFixer("a", claims=False)
        registry = FixerRegistry([a])

        snapshot = registry.fixers
        snapshot.clear()

        # Mutating the returned list doesn't affect the registry.
        assert len(registry.fixers) == 1


class TestFaultFixerProtocol:
    """Structural typing — any class with the right shape satisfies FaultFixer."""

    def test_recording_fixer_satisfies_protocol(self) -> None:
        fixer: FaultFixer = _RecordingFixer("x", claims=True)
        assert fixer.name == "x"


class TestSerializationRoundtrip:
    """Pydantic v2 must roundtrip a LifecycleState carrying FixOutcome+FixProposal."""

    def test_state_with_outcome_and_proposal_roundtrips(self) -> None:
        from rpa_architect.lifecycle.state import (
            FixProposal,
            LifecycleRequest,
            LifecycleState,
            ProposedChange,
        )

        outcome = FixOutcome(
            fixer="fix_proposal",
            success=False,
            requires_escalation=True,
            diagnosis_category="selector_drift",
            proposal=FixProposal(
                description="Re-harvest selectors",
                changes=[
                    ProposedChange(
                        file_path=".objects/x.json", change_type="modify", description="re-harvest"
                    )
                ],
                risk_level="medium",
            ),
            evidence={"synthesized_category": "selector_drift"},
        )

        from rpa_architect.lifecycle.state import FixOutputs

        state = LifecycleState(
            request=LifecycleRequest(source="x", source_type="pdd"),
            fix=FixOutputs(outcome=outcome, history=[outcome]),
        )

        dumped = state.model_dump()
        # Outcome is a stdlib frozen dataclass — model_dump descends into it.
        assert dumped["fix"]["outcome"]["fixer"] == "fix_proposal"
        assert dumped["fix"]["outcome"]["proposal"]["description"] == "Re-harvest selectors"
        assert len(dumped["fix"]["outcome"]["proposal"]["changes"]) == 1

        # Field shape: legacy flat names must NOT appear at top level after the
        # FixOutputs / MonitoringOutputs migrations. Locks in the new schema.
        assert "last_fix_outcome" not in dumped
        assert "fix_history" not in dumped
        assert "approval_status" not in dumped
        assert "monitoring_report" not in dumped
        assert "diagnosis" not in dumped
        assert "drift_report" not in dumped
        assert "monitoring" in dumped
        assert "fix" in dumped


class TestSwarmThenCatchAllRouting:
    """End-to-end: registry routes XAML failures to swarm, others to catch-all."""

    @pytest.mark.asyncio
    async def test_xaml_failure_goes_to_swarm(self) -> None:
        import tempfile

        from rpa_architect.lifecycle.fix_proposal_fixer import FixProposalFixer
        from rpa_architect.lifecycle.state import FixCandidate, XamlPatch
        from rpa_architect.lifecycle.swarm.arbiter import ArbiterVerdict
        from rpa_architect.lifecycle.swarm.graph import SwarmVerdict
        from rpa_architect.lifecycle.swarm_fault_fixer import SwarmFaultFixer

        winner = FixCandidate(
            specialist="selector_repair",
            confidence=0.9,
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
        )
        scripted = SwarmVerdict(
            bundle=FailureBundle(job_id="j", process_key="p", state="Faulted"),
            arbiter_verdict=ArbiterVerdict(
                winner=winner, considered=[winner], requires_escalation=False, rationale="picked"
            ),
            staging=None,
            staging_success=True,
            pr_url="https://x/pr/1",
            requires_escalation=False,
            candidates=[winner],
        )

        class _FakeOrch:
            async def heal_bundle(self, bundle):
                return scripted

        with tempfile.TemporaryDirectory() as tmp:
            registry = FixerRegistry(
                [
                    SwarmFaultFixer(orchestrator=_FakeOrch()),
                    FixProposalFixer(project_dir=tmp),
                ]
            )
            bundle = FailureBundle(
                job_id="j",
                process_key="p",
                state="Faulted",
                xaml_files={"Main.xaml": "<Activity/>"},
            )
            outcome = await registry.remediate(bundle)

            assert outcome.fixer == "swarm"
            assert outcome.delivery_url == "https://x/pr/1"

    @pytest.mark.asyncio
    async def test_non_xaml_failure_falls_through_to_catch_all(self) -> None:
        import tempfile

        from rpa_architect.lifecycle.fix_proposal_fixer import FixProposalFixer
        from rpa_architect.lifecycle.swarm_fault_fixer import SwarmFaultFixer

        class _NeverCalledOrch:
            async def heal_bundle(self, bundle):  # pragma: no cover
                raise AssertionError("swarm should not be invoked when xaml_files is empty")

        with tempfile.TemporaryDirectory() as tmp:
            registry = FixerRegistry(
                [
                    SwarmFaultFixer(orchestrator=_NeverCalledOrch()),
                    FixProposalFixer(project_dir=tmp),
                ]
            )
            # No xaml_files — swarm declines.
            outcome = await registry.remediate(
                FailureBundle(
                    job_id="j",
                    process_key="p",
                    state="Faulted",
                    exception_type="VerySpecificError",
                )
            )

            assert outcome.fixer == "fix_proposal"
            assert outcome.requires_escalation is True
