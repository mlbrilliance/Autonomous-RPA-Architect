"""Three rule-based specialists that react to non-selector failure categories.

Selector repair is complex enough to live in its own module
(:mod:`rpa_architect.lifecycle.swarm.selector_repair`). These three are
stateless heuristics — each inspects the :class:`FailureBundle` exception
type and either returns a :class:`FixCandidate` or ``None``.

Contract every specialist obeys:

* ``propose(bundle, xaml_docs, *, target_url)`` returns ``FixCandidate | None``.
* Returning ``None`` means "I have no opinion"; the arbiter silently skips.
* The four specialists are mutually exclusive *in practice* — exceptions
  fall into one class — but the arbiter tolerates multiple candidates
  firing and picks the highest-confidence one that compiles.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rpa_architect.lifecycle.state import FailureBundle, FixCandidate
from rpa_architect.xaml_ast import XamlDocument


@runtime_checkable
class Specialist(Protocol):
    """Structural type every specialist satisfies."""

    async def propose(
        self,
        bundle: FailureBundle,
        xaml_docs: dict[str, XamlDocument],
        *,
        target_url: str | None,
    ) -> FixCandidate | None: ...


class NullExceptionSpecialist:
    """Reacts to ``NullReferenceException`` / ``ArgumentNullException`` failures.

    Does not auto-patch XAML (null guards require semantic understanding of
    the surrounding activity). Emits a low-confidence candidate that
    categorizes the failure as ``code_bug`` and asks for human review.
    """

    name = "null_exception"

    async def propose(
        self,
        bundle: FailureBundle,
        xaml_docs: dict[str, XamlDocument],
        *,
        target_url: str | None,
    ) -> FixCandidate | None:
        etype = bundle.exception_type
        if etype not in {"NullReferenceException", "ArgumentNullException"}:
            return None
        return FixCandidate(
            specialist=self.name,
            confidence=0.45,
            diagnosis_category="code_bug",
            patches=[],
            reasoning=(
                f"{etype} thrown at runtime. A missing variable initialization "
                "or an external API returning null is likely. Recommend wrapping "
                "the activity in an If-Is-Nothing guard with a BusinessRuleException "
                "fallback — review in Studio before applying."
            ),
        )


class TimingRepairSpecialist:
    """Reacts to ``TimeoutException`` failures.

    First-line repair is bumping the Timeout attribute on the nearest Target
    element, but choosing the bump amount responsibly requires runtime data
    we don't have here. We emit a medium-confidence candidate that the
    arbiter's staging validator can exercise once the user approves.
    """

    name = "timing_repair"

    async def propose(
        self,
        bundle: FailureBundle,
        xaml_docs: dict[str, XamlDocument],
        *,
        target_url: str | None,
    ) -> FixCandidate | None:
        if bundle.exception_type != "TimeoutException":
            return None
        return FixCandidate(
            specialist=self.name,
            confidence=0.55,
            diagnosis_category="system_timeout",
            patches=[],
            reasoning=(
                "TimeoutException suggests the target element wasn't INTERACTIVE "
                "within the default window. Recommend raising Target.Timeout "
                "to 10000ms and adding a Retry scope around the activity. "
                "Patches omitted because target activity is ambiguous from "
                "the exception text alone — arbiter should route to human "
                "review or a targeted selector inspection."
            ),
        )


class BusinessRuleSpecialist:
    """Reacts to ``BusinessRuleException`` — always escalates, never patches.

    Business rules are semantic; a coding agent cannot (and should not)
    decide whether raising a threshold is the right fix. This specialist
    exists so the swarm's routing is complete — without it, business-rule
    failures would fall through to the selector repair agent, which has no
    signal for them.
    """

    name = "business_rule"

    async def propose(
        self,
        bundle: FailureBundle,
        xaml_docs: dict[str, XamlDocument],
        *,
        target_url: str | None,
    ) -> FixCandidate | None:
        if bundle.exception_type != "BusinessRuleException":
            return None
        return FixCandidate(
            specialist=self.name,
            confidence=0.9,
            diagnosis_category="business_rule_violation",
            patches=[],
            reasoning=(
                "BusinessRuleException is a deliberate signal from the process "
                "rules, not a bug. The swarm will not auto-patch; instead the "
                "candidate escalates to human review with the exception message "
                "and rule context attached."
            ),
        )
