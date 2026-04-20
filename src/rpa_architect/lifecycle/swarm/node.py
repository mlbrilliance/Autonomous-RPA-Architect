"""LangGraph node that wraps :class:`SwarmOrchestrator` for the lifecycle graph.

The node is built as a closure around a fully-constructed orchestrator so the
graph wiring stays declarative. When the monitoring report has at least one
faulted job with a job id, the node invokes ``orchestrator.heal`` and records
the outcome on :class:`LifecycleState`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from rpa_architect.lifecycle.state import LifecycleEvent, LifecyclePhase, LifecycleState
from rpa_architect.lifecycle.swarm.graph import SwarmOrchestrator

logger = logging.getLogger("rpa_architect.lifecycle.swarm.node")


def build_swarm_node(
    orchestrator: SwarmOrchestrator,
) -> Callable[[LifecycleState], Coroutine[Any, Any, LifecycleState]]:
    """Return a LangGraph-compatible node that heals the first faulted job it sees."""

    async def swarm_node(state: LifecycleState) -> LifecycleState:
        state.phase = LifecyclePhase.DIAGNOSING
        report = state.monitoring_report
        if not report or not report.failed_jobs:
            state.swarm_requires_escalation = True
            _event(state, "swarm_skipped", "no faulted jobs to heal")
            return state

        job_id = report.failed_jobs[0].job_id
        try:
            verdict = await orchestrator.heal(job_id=job_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("swarm_node: heal failed for job %s", job_id)
            state.swarm_requires_escalation = True
            state.errors.append(f"swarm heal failed: {exc}")
            _event(state, "swarm_error", str(exc))
            return state

        state.swarm_pr_url = verdict.pr_url
        state.swarm_requires_escalation = verdict.requires_escalation
        _event(
            state,
            "swarm_heal",
            (
                f"job={job_id} pr={verdict.pr_url or 'none'} "
                f"staging_success={verdict.staging_success} "
                f"requires_escalation={verdict.requires_escalation}"
            ),
            metadata={
                "candidates": [c.specialist for c in verdict.candidates],
                "winner": (
                    verdict.arbiter_verdict.winner.specialist
                    if verdict.arbiter_verdict.winner
                    else ""
                ),
            },
        )
        return state

    return swarm_node


def _event(state: LifecycleState, evt: str, detail: str, *, metadata: dict | None = None) -> None:
    state.history.append(
        LifecycleEvent(
            phase=state.phase,
            event_type=evt,
            detail=detail,
            metadata=metadata or {},
        )
    )
