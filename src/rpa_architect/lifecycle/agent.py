"""LangGraph lifecycle agent: author → deploy → monitor → diagnose → fix loop.

The fault-fix branch is driven by a :class:`FixerRegistry`. Three call shapes:

- ``create_lifecycle_graph(swarm=…)`` — legacy. Builds
  ``[SwarmFaultFixer, FixProposalFixer]`` and reuses ``swarm.fetcher``.
- ``create_lifecycle_graph(fixer_registry=…, fetcher=…)`` — caller
  controls the full pipeline.
- ``create_lifecycle_graph()`` — defaults to ``[FixProposalFixer]`` with
  no fetcher; ``fix_node`` synthesizes a lean :class:`FailureBundle` from
  ``state.monitoring.report.failed_jobs[0]``.

Lifecycle routing reads ``state.fix.outcome`` — adapters do not
populate adapter-specific fields on ``LifecycleState``.
"""

from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from rpa_architect.lifecycle.fault_fixer import FixerRegistry
from rpa_architect.lifecycle.fix_node import FailureBundleFetcherLike
from rpa_architect.lifecycle.state import LifecycleState
from rpa_architect.lifecycle.swarm.graph import SwarmOrchestrator

logger = logging.getLogger(__name__)


def _route_after_validate(state: LifecycleState) -> str:
    """After validation: deploy if clean, else check iteration budget."""
    if not state.errors:
        return "deploy"
    if state.iteration < state.max_iterations:
        return "author"  # re-generate with error feedback
    logger.warning("Validation exhausted %d iterations — deploying best result.", state.iteration)
    return "deploy"


def _route_after_monitor(state: LifecycleState) -> str:
    """After monitoring: diagnose failures, or end if healthy."""
    report = state.monitoring.report
    if report and report.faulted > 0:
        return "diagnose"
    return END


def _route_after_diagnose(state: LifecycleState) -> str:
    """After diagnosis: hand to fix_node, or end if no fix is recommended."""
    diag = state.monitoring.diagnosis
    if diag and diag.recommended_action in ("fix_code", "update_selectors", "update_config"):
        return "fix"
    return END  # escalate / no_action / retry — lifecycle ends, human takes over


def _route_after_approval(state: LifecycleState) -> str:
    """After approval gate: apply fix if approved, otherwise end."""
    if state.fix.approval_status == "approved":
        return "apply_fix"
    return END


def _route_after_apply(state: LifecycleState) -> str:
    """After applying fix: re-validate and redeploy, or end if budget exhausted."""
    if state.iteration < state.max_iterations:
        return "validate_gate"
    return END


def _resolve_fixer_pipeline(
    swarm: SwarmOrchestrator | None,
    fixer_registry: FixerRegistry | None,
    fetcher: FailureBundleFetcherLike | None,
) -> tuple[FixerRegistry, FailureBundleFetcherLike | None]:
    """Choose the fixer registry + bundle fetcher for the lifecycle graph.

    Three valid call shapes (see module docstring). Mixing ``swarm`` with
    ``fixer_registry`` is rejected to keep wiring deterministic.
    """
    if fixer_registry is not None and swarm is not None:
        raise ValueError("Pass either `swarm=` or `fixer_registry=`, not both.")

    if fixer_registry is not None:
        return fixer_registry, fetcher  # fetcher may be None — fix_node synthesizes

    if swarm is not None:
        from rpa_architect.lifecycle.fix_proposal_fixer import FixProposalFixer
        from rpa_architect.lifecycle.migrator_qa_fixer import MigratorQAFixer
        from rpa_architect.lifecycle.swarm_fault_fixer import SwarmFaultFixer

        # Order: MigratorQAFixer first because its ``can_handle`` is mutex with
        # SwarmFaultFixer's (xaml_files vs project_dir/main.py). FixProposalFixer
        # remains the catch-all tail for anything neither claims.
        registry = FixerRegistry(
            [
                MigratorQAFixer(),
                SwarmFaultFixer(orchestrator=swarm),
                FixProposalFixer(project_dir=str(swarm.repo_root)),
            ]
        )
        return registry, swarm.fetcher

    # No-args default: migrator fixer + catch-all, bundle synthesized from state.
    from rpa_architect.lifecycle.fix_proposal_fixer import FixProposalFixer
    from rpa_architect.lifecycle.migrator_qa_fixer import MigratorQAFixer

    return FixerRegistry([MigratorQAFixer(), FixProposalFixer(project_dir="")]), None


def create_lifecycle_graph(
    swarm: SwarmOrchestrator | None = None,
    *,
    fixer_registry: FixerRegistry | None = None,
    fetcher: FailureBundleFetcherLike | None = None,
) -> CompiledStateGraph:
    """Build and compile the lifecycle agent graph.

    Topology::

        author → validate_gate ─┬─(clean)──→ deploy → monitor ─┬─(healthy)──→ END
                                 │                               │
                                 └─(errors, budget)──→ author    └─(faulted)──→ diagnose
                                 └─(errors, exhausted)→ deploy        │
                                                                      fix ─┬─(success+pr)──→ END
                                                                           │
                                                                           └─(escalate)──→ approval_gate
                                                                                                │
                                                                                          ┌──(approved)
                                                                                          │
                                                                                     apply_fix ←──┘
                                                                                          │
                                                                                   validate_gate (loop)
    """
    from rpa_architect.lifecycle.fix_node import build_fix_node, route_after_fix
    from rpa_architect.lifecycle.nodes import (
        apply_fix_node,
        approval_gate_node,
        author_node,
        deploy_node,
        diagnose_node,
        monitor_node,
        validate_gate_node,
    )

    graph = StateGraph(LifecycleState)

    graph.add_node("author", author_node)
    graph.add_node("validate_gate", validate_gate_node)
    graph.add_node("deploy", deploy_node)
    graph.add_node("monitor", monitor_node)
    graph.add_node("diagnose", diagnose_node)
    graph.add_node("approval_gate", approval_gate_node)
    graph.add_node("apply_fix", apply_fix_node)

    registry, fix_fetcher = _resolve_fixer_pipeline(swarm, fixer_registry, fetcher)
    graph.add_node("fix", build_fix_node(registry=registry, fetcher=fix_fetcher))

    graph.set_entry_point("author")

    graph.add_edge("author", "validate_gate")

    graph.add_conditional_edges(
        "validate_gate",
        _route_after_validate,
        {"deploy": "deploy", "author": "author"},
    )

    graph.add_edge("deploy", "monitor")

    graph.add_conditional_edges(
        "monitor",
        _route_after_monitor,
        {"diagnose": "diagnose", END: END},
    )

    graph.add_conditional_edges(
        "diagnose",
        _route_after_diagnose,
        {"fix": "fix", END: END},
    )

    graph.add_conditional_edges(
        "fix",
        route_after_fix,
        {"approval_gate": "approval_gate", END: END},
    )

    graph.add_conditional_edges(
        "approval_gate",
        _route_after_approval,
        {"apply_fix": "apply_fix", END: END},
    )

    graph.add_conditional_edges(
        "apply_fix",
        _route_after_apply,
        {"validate_gate": "validate_gate", END: END},
    )

    return graph.compile()
