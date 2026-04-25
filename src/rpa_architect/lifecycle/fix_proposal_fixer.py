"""FixProposalFixer — catch-all FaultFixer that escalates for human approval.

Wraps the older :func:`lifecycle.fix_proposer.generate_fix_proposal` path so
the registry has a safety net for any failure the swarm declines or fails
to repair. ``can_handle`` always returns True; ``fix`` synthesizes a
:class:`DiagnosisResult` from the :class:`FailureBundle`, generates a
:class:`FixProposal`, and emits a :class:`FixOutcome` with
``requires_escalation=True`` — this path never auto-merges.

Synthesis lives here, not in fix_proposer, so the older entry-point keeps
its DiagnosisResult input contract.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from rpa_architect.lifecycle.fault_fixer import FixOutcome
from rpa_architect.lifecycle.fix_proposer import generate_fix_proposal
from rpa_architect.lifecycle.state import DiagnosisResult, FailureBundle

logger = logging.getLogger(__name__)


# exception_type substring → (DiagnosisResult.category, recommended_action)
_EXCEPTION_TYPE_MAP: tuple[tuple[str, str, str], ...] = (
    ("Selector", "selector_drift", "update_selectors"),
    ("Null", "code_bug", "fix_code"),
    ("Timeout", "system_timeout", "escalate_to_human"),
    ("BusinessRule", "business_rule_violation", "update_config"),
    ("Credential", "credential_expiry", "escalate_to_human"),
    ("Schema", "data_schema_change", "update_config"),
)


def synthesize_diagnosis(failure: FailureBundle) -> DiagnosisResult:
    """Build a minimal DiagnosisResult from a FailureBundle.

    Heuristic: substring-match the exception_type. Anything unmatched (or
    empty) becomes ``unknown`` — fix_proposer's strategy table routes that
    to the escalation proposal.
    """
    category: Any = "unknown"
    action: Any = "escalate_to_human"
    for needle, cat, act in _EXCEPTION_TYPE_MAP:
        if needle.lower() in failure.exception_type.lower():
            category, action = cat, act
            break

    evidence: list[str] = []
    if failure.exception_message:
        evidence.append(f"exception_message: {failure.exception_message}")
    if failure.exception_type:
        evidence.append(f"exception_type: {failure.exception_type}")

    return DiagnosisResult(
        root_cause=failure.exception_message or failure.exception_type or "unknown failure",
        category=category,
        affected_files=list(failure.xaml_files.keys()),
        confidence=0.4,
        recommended_action=action,
        evidence=evidence,
    )


@dataclass
class FixProposalFixer:
    """Catch-all adapter — every failure produces a proposal for human review."""

    project_dir: str
    name: str = "fix_proposal"

    async def can_handle(self, failure: FailureBundle) -> bool:
        return True

    async def fix(self, failure: FailureBundle) -> FixOutcome:
        # Prefer project_dir from the bundle (set by fix_node from
        # state.authoring.project_dir) so the catch-all sees the live project,
        # not the path captured when this adapter was constructed.
        project_dir = failure.project_dir or self.project_dir
        diagnosis = synthesize_diagnosis(failure)
        try:
            proposal = await generate_fix_proposal(diagnosis, project_dir, ir={})
        except Exception as exc:  # noqa: BLE001 — catch-all must never propagate
            logger.exception("fix_proposal: generate_fix_proposal raised")
            return FixOutcome(
                fixer=self.name,
                success=False,
                requires_escalation=True,
                delivery_url="",
                diagnosis_category=diagnosis.category,
                evidence={
                    "synthesized_category": diagnosis.category,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )

        evidence: dict[str, Any] = {
            "synthesized_category": diagnosis.category,
        }

        return FixOutcome(
            fixer=self.name,
            success=False,
            requires_escalation=True,
            delivery_url="",
            diagnosis_category=diagnosis.category,
            proposal=proposal,
            evidence=evidence,
        )
