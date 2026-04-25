"""FaultFixer Protocol — pluggable adapters that remediate one kind of failure.

The lifecycle layer hands each :class:`FailureBundle` to a registry of
fixers in priority order. The first whose :meth:`FaultFixer.can_handle`
returns ``True`` is asked to :meth:`FaultFixer.fix` the failure. Fixers
are mutually exclusive at this layer — any fan-out + arbitration (as in
the self-healing swarm) is the fixer's private business.

Adding a new remediation strategy is one new module + one line in the
registry. ``LifecycleState`` carries the resulting :class:`FixOutcome`
in a single field, regardless of which adapter ran.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from rpa_architect.lifecycle.state import FailureBundle, FixProposal


@dataclass(frozen=True)
class FixOutcome:
    """The result of one remediation attempt.

    Lifecycle nodes after the fix step read only this dataclass — they do
    not branch on which adapter ran. ``requires_escalation`` is the single
    signal that routes to human-approval; ``delivery_url`` is whatever
    artifact the adapter produced (PR url, ticket url, '' if none).

    ``proposal`` is the typed deliverable for the human-approval path —
    populated only by ``FixProposalFixer``. The approval_gate / apply_fix
    nodes read it when ``requires_escalation`` is True. Other adapters
    leave it None.
    """

    fixer: str
    success: bool
    requires_escalation: bool
    delivery_url: str = ""
    diagnosis_category: str = "unknown"
    proposal: "FixProposal | None" = None
    evidence: dict[str, Any] = field(default_factory=dict)


class FaultFixer(Protocol):
    """Structural interface every fault-fixer adapter satisfies.

    ``can_handle`` is async so future adapters can do live probes (e.g.,
    ping a service endpoint to decide ownership) without a breaking
    interface change. Synchronous implementations just ``return bool(...)``.
    """

    name: str

    async def can_handle(self, failure: FailureBundle) -> bool: ...

    async def fix(self, failure: FailureBundle) -> FixOutcome: ...


class FixerRegistry:
    """Ordered list of fixers; first matching ``can_handle`` wins.

    Empty registry or no-match both produce a catch-all escalation outcome
    rather than raising — fail-safe is the right default for operational
    remediation code.
    """

    def __init__(self, fixers: list[FaultFixer]) -> None:
        self._fixers: list[FaultFixer] = list(fixers)

    @property
    def fixers(self) -> list[FaultFixer]:
        return list(self._fixers)

    async def remediate(self, failure: FailureBundle) -> FixOutcome:
        for fixer in self._fixers:
            if await fixer.can_handle(failure):
                return await fixer.fix(failure)
        return FixOutcome(
            fixer="none",
            success=False,
            requires_escalation=True,
            evidence={"reason": "no fixer claimed the failure"},
        )
