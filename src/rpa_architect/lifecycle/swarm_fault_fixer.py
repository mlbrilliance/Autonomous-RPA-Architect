"""SwarmFaultFixer — FaultFixer adapter wrapping the Self-Healing Swarm.

Maps :class:`SwarmVerdict` to :class:`FixOutcome` so the lifecycle layer
treats swarm-driven repair as one option among many. The swarm's internal
fan-out + arbitration is private to this adapter.

Claim rule: the swarm needs deployed XAML to patch — if the bundle
carries no ``xaml_files``, no specialist can do anything useful, so we
decline and let a later fixer (e.g. the catch-all) take over.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from rpa_architect.lifecycle.fault_fixer import FixOutcome
from rpa_architect.lifecycle.state import FailureBundle
from rpa_architect.lifecycle.swarm.graph import SwarmVerdict


class SwarmHealer(Protocol):
    """Subset of :class:`SwarmOrchestrator` the adapter depends on."""

    async def heal_bundle(self, bundle: FailureBundle) -> SwarmVerdict: ...


@dataclass
class SwarmFaultFixer:
    """Wraps a :class:`SwarmOrchestrator` as a :class:`FaultFixer`."""

    orchestrator: SwarmHealer
    name: str = "swarm"

    async def can_handle(self, failure: FailureBundle) -> bool:
        return bool(failure.xaml_files)

    async def fix(self, failure: FailureBundle) -> FixOutcome:
        verdict = await self.orchestrator.heal_bundle(failure)
        winner = verdict.arbiter_verdict.winner

        evidence: dict[str, Any] = {
            "specialist": winner.specialist if winner else "",
            "confidence": winner.confidence if winner else 0.0,
            "candidate_count": len(verdict.candidates),
            "staging_success": verdict.staging_success,
            "rationale": verdict.arbiter_verdict.rationale,
        }
        if verdict.staging is not None:
            evidence["staging_message"] = verdict.staging.message

        return FixOutcome(
            fixer=self.name,
            success=(not verdict.requires_escalation) and bool(verdict.pr_url),
            requires_escalation=verdict.requires_escalation,
            delivery_url=verdict.pr_url,
            diagnosis_category=winner.diagnosis_category if winner else "unknown",
            evidence=evidence,
        )
