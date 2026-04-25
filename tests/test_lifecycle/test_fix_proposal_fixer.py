"""Contract tests for FixProposalFixer — the catch-all adapter."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from rpa_architect.lifecycle.fault_fixer import FaultFixer, FixOutcome
from rpa_architect.lifecycle.fix_proposal_fixer import (
    FixProposalFixer,
    synthesize_diagnosis,
)
from rpa_architect.lifecycle.state import FailureBundle


def _bundle(*, exception_type: str = "", exception_message: str = "boom") -> FailureBundle:
    return FailureBundle(
        job_id="job-7",
        process_key="ProcessInvoice",
        state="Faulted",
        exception_message=exception_message,
        exception_type=exception_type,
    )


class TestSynthesizeDiagnosis:
    """Heuristic mapping from FailureBundle.exception_type → DiagnosisResult.category."""

    def test_selector_exception_maps_to_selector_drift(self) -> None:
        d = synthesize_diagnosis(_bundle(exception_type="SelectorNotFoundException"))
        assert d.category == "selector_drift"
        assert d.recommended_action == "update_selectors"

    def test_null_exception_maps_to_code_bug(self) -> None:
        d = synthesize_diagnosis(_bundle(exception_type="NullReferenceException"))
        assert d.category == "code_bug"

    def test_timeout_maps_to_system_timeout(self) -> None:
        d = synthesize_diagnosis(_bundle(exception_type="TimeoutException"))
        assert d.category == "system_timeout"

    def test_business_rule_maps_to_business_rule_violation(self) -> None:
        d = synthesize_diagnosis(_bundle(exception_type="BusinessRuleException"))
        assert d.category == "business_rule_violation"

    def test_unknown_exception_falls_back_to_unknown(self) -> None:
        d = synthesize_diagnosis(_bundle(exception_type="WeirdCustomError"))
        assert d.category == "unknown"

    def test_empty_exception_type_maps_to_unknown(self) -> None:
        d = synthesize_diagnosis(_bundle(exception_type=""))
        assert d.category == "unknown"

    def test_synthesized_evidence_includes_exception_message(self) -> None:
        d = synthesize_diagnosis(_bundle(exception_type="X", exception_message="lookup failed"))
        assert any("lookup failed" in line for line in d.evidence)


class TestCanHandle:
    @pytest.mark.asyncio
    async def test_always_claims_as_catch_all(self) -> None:
        fixer = FixProposalFixer(project_dir="/tmp")
        # Empty bundle: still claimed.
        assert await fixer.can_handle(_bundle()) is True
        # Bundle with exception: still claimed.
        assert await fixer.can_handle(_bundle(exception_type="anything")) is True


class TestFix:
    @pytest.mark.asyncio
    async def test_always_requires_escalation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixer = FixProposalFixer(project_dir=tmp)
            outcome = await fixer.fix(_bundle(exception_type="SelectorNotFoundException"))

            assert outcome.fixer == "fix_proposal"
            assert outcome.requires_escalation is True
            # Catch-all never auto-merges — success is False even when a proposal is generated.
            assert outcome.success is False

    @pytest.mark.asyncio
    async def test_diagnosis_category_propagates_to_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixer = FixProposalFixer(project_dir=tmp)
            outcome = await fixer.fix(_bundle(exception_type="SelectorNotFoundException"))
            assert outcome.diagnosis_category == "selector_drift"

    @pytest.mark.asyncio
    async def test_unknown_exception_does_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixer = FixProposalFixer(project_dir=tmp)
            outcome = await fixer.fix(_bundle(exception_type="VeryRareError"))
            assert outcome.diagnosis_category == "unknown"

    @pytest.mark.asyncio
    async def test_outcome_carries_typed_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / ".objects").mkdir()
            (project / ".objects" / "selector_a.json").write_text("{}")

            fixer = FixProposalFixer(project_dir=str(project))
            outcome = await fixer.fix(_bundle(exception_type="SelectorNotFoundException"))

            # Typed proposal lands on outcome — not in untyped evidence dict.
            assert outcome.proposal is not None
            assert outcome.proposal.proposal_id
            assert outcome.proposal.risk_level in ("low", "medium", "high")
            assert len(outcome.proposal.changes) >= 1
            # Synthesized category is the only evidence key now.
            assert outcome.evidence == {"synthesized_category": "selector_drift"}

    @pytest.mark.asyncio
    async def test_delivery_url_is_empty_pre_human_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixer = FixProposalFixer(project_dir=tmp)
            outcome = await fixer.fix(_bundle(exception_type="SelectorNotFoundException"))
            # No PR / ticket yet — that's the human's job.
            assert outcome.delivery_url == ""


class TestProjectDirOverride:
    """The bundle's project_dir takes precedence over the constructor arg."""

    @pytest.mark.asyncio
    async def test_bundle_project_dir_overrides_constructor(self) -> None:
        with tempfile.TemporaryDirectory() as live_project:
            # Constructor was given a stale path; bundle has the live one.
            stale = "/some/stale/path"
            fixer = FixProposalFixer(project_dir=stale)
            bundle = FailureBundle(
                job_id="j",
                process_key="p",
                state="Faulted",
                exception_type="SelectorNotFoundException",
                project_dir=live_project,
            )

            outcome = await fixer.fix(bundle)

            # Proposal generated against live_project, not stale.
            assert outcome.proposal is not None
            # Stale path would have raised or produced empty changes;
            # live_project at least exists.

    @pytest.mark.asyncio
    async def test_constructor_path_used_when_bundle_has_none(self) -> None:
        with tempfile.TemporaryDirectory() as ctor_project:
            fixer = FixProposalFixer(project_dir=ctor_project)
            bundle = FailureBundle(
                job_id="j",
                process_key="p",
                state="Faulted",
                exception_type="SelectorNotFoundException",
                # project_dir defaults to "" — fixer should fall back.
            )
            outcome = await fixer.fix(bundle)
            assert outcome.proposal is not None


class TestExceptionHandling:
    """Catch-all must never propagate — even if the wrapped fix_proposer crashes."""

    @pytest.mark.asyncio
    async def test_fix_proposer_exception_returns_escalation_outcome(self, monkeypatch) -> None:
        async def boom(*args, **kwargs):
            raise RuntimeError("fix_proposer exploded")

        monkeypatch.setattr(
            "rpa_architect.lifecycle.fix_proposal_fixer.generate_fix_proposal", boom
        )

        with tempfile.TemporaryDirectory() as tmp:
            fixer = FixProposalFixer(project_dir=tmp)
            outcome = await fixer.fix(_bundle(exception_type="SelectorNotFoundException"))

            # Catch-all must never let exceptions escape — that would leave the
            # registry without a fallback FixOutcome.
            assert outcome.fixer == "fix_proposal"
            assert outcome.requires_escalation is True
            assert outcome.success is False
            assert outcome.proposal is None
            assert outcome.evidence["error_type"] == "RuntimeError"
            assert "fix_proposer exploded" in outcome.evidence["error"]
            assert outcome.diagnosis_category == "selector_drift"


class TestProtocolConformance:
    def test_satisfies_fault_fixer_protocol(self) -> None:
        fixer: FaultFixer = FixProposalFixer(project_dir="/tmp")
        assert fixer.name == "fix_proposal"

    @pytest.mark.asyncio
    async def test_returns_fix_outcome_instance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixer = FixProposalFixer(project_dir=tmp)
            outcome = await fixer.fix(_bundle())
            assert isinstance(outcome, FixOutcome)
