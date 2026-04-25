"""Unified fix_node — runs FixerRegistry against the first faulted job.

Replaces the swarm-specific ``swarm_node``: lifecycle routing now reads
``state.fix.outcome.requires_escalation`` regardless of which adapter
ran.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any, Protocol

from langgraph.graph import END

from rpa_architect.lifecycle.fault_fixer import FixOutcome, FixerRegistry
from rpa_architect.lifecycle.state import (
    FailureBundle,
    LifecycleEvent,
    LifecyclePhase,
    LifecycleState,
)

logger = logging.getLogger(__name__)


class FailureBundleFetcherLike(Protocol):
    async def fetch(self, job_id: str) -> FailureBundle: ...


def build_fix_node(
    *,
    registry: FixerRegistry,
    fetcher: FailureBundleFetcherLike | None = None,
) -> Callable[[LifecycleState], Coroutine[Any, Any, LifecycleState]]:
    """Build the LangGraph-compatible fix node.

    The node:
    1. Picks the first faulted job from the monitoring report.
    2. Builds a :class:`FailureBundle` — via ``fetcher`` if provided
       (rich bundle: pulls XAML files from the deployed package), or
       synthesized from the monitoring report's failed-job record
       (lean bundle: no XAML, sufficient for non-swarm catch-all flows).
    3. Runs the registry; first matching fixer wins.
    4. Records the outcome on ``state.fix.outcome`` + ``fix_history``.
    """

    async def fix_node(state: LifecycleState) -> LifecycleState:
        state.phase = LifecyclePhase.DIAGNOSING
        report = state.monitoring.report
        if not report or not report.failed_jobs:
            outcome = FixOutcome(
                fixer="none",
                success=False,
                requires_escalation=True,
                evidence={"reason": "no faulted jobs to remediate"},
            )
            _record(state, outcome, "fix_skipped", "no faulted jobs to heal")
            return state

        failed = report.failed_jobs[0]
        try:
            if fetcher is not None:
                bundle = await fetcher.fetch(failed.job_id)
            else:
                bundle = _synthesize_bundle(report.process_key, failed, state.authoring.project_dir)
        except Exception as exc:  # noqa: BLE001 — fetcher boundary; convert to outcome
            logger.exception("fix_node: fetcher raised for job %s", failed.job_id)
            outcome = FixOutcome(
                fixer="none",
                success=False,
                requires_escalation=True,
                evidence={
                    "reason": "failed to fetch failure bundle",
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "job_id": failed.job_id,
                },
            )
            state.errors.append(f"fix_node fetcher failed: {exc}")
            _record(state, outcome, "fix_error", str(exc))
            return state

        outcome = await registry.remediate(bundle)
        _record(
            state,
            outcome,
            "fix_remediate",
            (
                f"job={failed.job_id} fixer={outcome.fixer} "
                f"success={outcome.success} escalate={outcome.requires_escalation}"
            ),
            metadata={"diagnosis_category": outcome.diagnosis_category},
        )
        return state

    return fix_node


def _synthesize_bundle(process_key: str, failed: Any, project_dir: str = "") -> FailureBundle:
    """Build a lean FailureBundle from the monitoring report's failed-job record.

    Used when no fetcher is wired (e.g. ``create_lifecycle_graph()`` with no
    swarm). Carries ``job_id``, ``state``, a heuristically parsed
    ``exception_type``, and ``project_dir`` so the catch-all
    ``FixProposalFixer`` can enumerate ``.objects/`` etc. at call time.
    ``xaml_files`` is empty, so ``SwarmFaultFixer`` correctly declines via
    its ``can_handle`` rule.
    """
    info = getattr(failed, "info", "") or ""
    exception_type = ""
    # ``ExecutionLog.info`` is typically "<ExceptionType>: <message>". Parse leniently.
    if ":" in info:
        head = info.split(":", 1)[0].strip()
        if head and " " not in head:
            exception_type = head
    return FailureBundle(
        job_id=failed.job_id,
        process_key=process_key,
        state=getattr(failed, "state", "Faulted"),
        exception_message=info,
        exception_type=exception_type,
        project_dir=project_dir,
    )


def route_after_fix(state: LifecycleState) -> str:
    """Lifecycle routing: success+delivery → END; escalation → approval_gate; else END."""
    out = state.fix.outcome
    if out is None:
        return END
    if out.success and out.delivery_url:
        return END
    if out.requires_escalation:
        return "approval_gate"
    return END


def _record(
    state: LifecycleState,
    outcome: FixOutcome,
    event_type: str,
    detail: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    state.fix.outcome = outcome
    state.fix.history.append(outcome)
    state.history.append(
        LifecycleEvent(
            phase=state.phase,
            event_type=event_type,
            detail=detail,
            metadata=metadata or {},
        )
    )
