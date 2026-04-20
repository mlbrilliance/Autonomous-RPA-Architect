"""Arbiter: consolidate N specialist proposals into a single verdict.

Decision rules (in order):

1. Prefer candidates that carry at least one patch — empty-patch candidates
   are diagnostic only and cannot be staged.
2. Among actionable candidates, pick the highest confidence.
3. If no candidate has patches, surface the highest-confidence diagnostic
   candidate with ``requires_escalation=True`` so the graph routes to the
   existing human-approval gate.
4. Empty slate → no winner, ``requires_escalation=True``.

The arbiter does not run ``xaml_lint`` or compile the patched XAML here —
that gate lives in the staging validator, where it is cheaper than
re-parsing every candidate twice. Keeping this module rule-pure makes
it trivial to test without any I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from rpa_architect.lifecycle.state import FixCandidate


@dataclass
class ArbiterVerdict:
    """The arbiter's output — what (if anything) to stage."""

    winner: FixCandidate | None
    considered: list[FixCandidate]
    requires_escalation: bool
    rationale: str


class Arbiter:
    """Stateless arbiter — one method, no I/O."""

    def arbitrate(self, candidates: list[FixCandidate]) -> ArbiterVerdict:
        if not candidates:
            return ArbiterVerdict(
                winner=None,
                considered=[],
                requires_escalation=True,
                rationale="no specialists returned a candidate",
            )

        patching = [c for c in candidates if c.patches]
        if patching:
            winner = max(patching, key=lambda c: c.confidence)
            return ArbiterVerdict(
                winner=winner,
                considered=candidates,
                requires_escalation=False,
                rationale=(
                    f"selected {winner.specialist} with confidence {winner.confidence:.2f} "
                    f"from {len(patching)} actionable candidate(s)"
                ),
            )

        # No actionable candidates — surface the strongest diagnostic for human review.
        winner = max(candidates, key=lambda c: c.confidence)
        return ArbiterVerdict(
            winner=winner,
            considered=candidates,
            requires_escalation=True,
            rationale=(
                f"no patchable candidate; escalating {winner.specialist} "
                f"(confidence {winner.confidence:.2f}) to human review"
            ),
        )
