"""Arbiter: pick the best FixCandidate from a slate."""

from __future__ import annotations

from rpa_architect.lifecycle.state import FixCandidate, XamlPatch
from rpa_architect.lifecycle.swarm.arbiter import Arbiter, ArbiterVerdict


def _patch() -> XamlPatch:
    return XamlPatch(
        file_path="Main.xaml",
        target_xpath="/a:Activity/a:Sequence",
        attribute="Selector",
        old_value="old",
        new_value="new",
    )


class TestArbiter:
    def test_picks_highest_confidence_with_patches(self) -> None:
        low = FixCandidate(specialist="null_exception", confidence=0.4, diagnosis_category="code_bug")
        high = FixCandidate(
            specialist="selector_repair",
            confidence=0.8,
            diagnosis_category="selector_drift",
            patches=[_patch()],
            patched_xaml={"Main.xaml": "<Activity/>"},
        )
        verdict = Arbiter().arbitrate([low, high])
        assert isinstance(verdict, ArbiterVerdict)
        assert verdict.winner is not None
        assert verdict.winner.specialist == "selector_repair"

    def test_skips_zero_patch_candidates_when_a_patching_candidate_exists(self) -> None:
        empty = FixCandidate(specialist="business_rule", confidence=0.95, diagnosis_category="business_rule_violation")
        patched = FixCandidate(
            specialist="selector_repair",
            confidence=0.6,
            diagnosis_category="selector_drift",
            patches=[_patch()],
            patched_xaml={"Main.xaml": "<Activity/>"},
        )
        verdict = Arbiter().arbitrate([empty, patched])
        # Even though business_rule has 0.95 confidence, it proposes no patch.
        # The arbiter prefers an actionable candidate.
        assert verdict.winner is not None
        assert verdict.winner.specialist == "selector_repair"

    def test_falls_back_to_escalation_when_no_patches(self) -> None:
        empty_a = FixCandidate(specialist="null_exception", confidence=0.4, diagnosis_category="code_bug")
        empty_b = FixCandidate(specialist="business_rule", confidence=0.9, diagnosis_category="business_rule_violation")
        verdict = Arbiter().arbitrate([empty_a, empty_b])
        # No patches available → winner is the highest-confidence escalation candidate
        assert verdict.winner is not None
        assert verdict.winner.specialist == "business_rule"
        assert verdict.requires_escalation is True

    def test_empty_slate_returns_no_winner(self) -> None:
        verdict = Arbiter().arbitrate([])
        assert verdict.winner is None
        assert verdict.requires_escalation is True
