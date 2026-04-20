"""LangGraph lifecycle agent: author → deploy → monitor → diagnose → fix loop.

With Task #5 the graph gains an optional Self-Healing Swarm branch. When
:func:`create_lifecycle_graph` is called without a swarm, the topology is
unchanged — the existing 1119 tests stay green. When called with a
``SwarmOrchestrator``, a new ``swarm_heal`` node runs after ``diagnose``
and either opens a PR (short-circuiting the propose_fix branch) or
escalates to the existing approval gate.
"""

from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

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
    report = state.monitoring_report
    if report and report.faulted > 0:
        return "diagnose"
    return END


def _route_after_diagnose(state: LifecycleState) -> str:
    """After diagnosis: propose fix or escalate to human."""
    diag = state.diagnosis
    if diag and diag.recommended_action in ("fix_code", "update_selectors", "update_config"):
        return "propose_fix"
    return END  # escalate / no_action / retry — lifecycle ends, human takes over


def _route_after_approval(state: LifecycleState) -> str:
    """After approval gate: apply fix if approved, otherwise end."""
    if state.approval_status == "approved":
        return "apply_fix"
    return END


def _route_after_apply(state: LifecycleState) -> str:
    """After applying fix: re-validate and redeploy, or end if budget exhausted."""
    if state.iteration < state.max_iterations:
        return "validate_gate"
    return END


def _route_after_swarm(state: LifecycleState) -> str:
    """After swarm: PR opened → END; escalation → propose_fix; error → END."""
    if state.swarm_pr_url:
        return END
    if state.swarm_requires_escalation:
        return "propose_fix"
    return END


def create_lifecycle_graph(
    swarm: SwarmOrchestrator | None = None,
) -> CompiledStateGraph:
    """Build and compile the lifecycle agent graph.

    Topology::

        author → validate_gate ─┬─(clean)──→ deploy → monitor ─┬─(healthy)──→ END
                                 │                               │
                                 └─(errors, budget)──→ author    └─(faulted)──→ diagnose
                                 └─(errors, exhausted)→ deploy        │
                                                                 propose_fix → approval_gate
                                                                      │              │
                                                                      │       ┌──(approved)
                                                                      │       │
                                                                 apply_fix ←──┘
                                                                      │
                                                               validate_gate (loop)
    """
    from rpa_architect.lifecycle.nodes import (
        apply_fix_node,
        approval_gate_node,
        author_node,
        deploy_node,
        diagnose_node,
        monitor_node,
        propose_fix_node,
        validate_gate_node,
    )

    graph = StateGraph(LifecycleState)

    graph.add_node("author", author_node)
    graph.add_node("validate_gate", validate_gate_node)
    graph.add_node("deploy", deploy_node)
    graph.add_node("monitor", monitor_node)
    graph.add_node("diagnose", diagnose_node)
    graph.add_node("propose_fix", propose_fix_node)
    graph.add_node("approval_gate", approval_gate_node)
    graph.add_node("apply_fix", apply_fix_node)

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

    if swarm is not None:
        from rpa_architect.lifecycle.swarm.node import build_swarm_node

        graph.add_node("swarm_heal", build_swarm_node(swarm))
        graph.add_conditional_edges(
            "diagnose",
            lambda s: "swarm_heal"
            if (s.diagnosis and s.diagnosis.recommended_action in ("fix_code", "update_selectors", "update_config"))
            else END,
            {"swarm_heal": "swarm_heal", END: END},
        )
        graph.add_conditional_edges(
            "swarm_heal",
            _route_after_swarm,
            {"propose_fix": "propose_fix", END: END},
        )
    else:
        graph.add_conditional_edges(
            "diagnose",
            _route_after_diagnose,
            {"propose_fix": "propose_fix", END: END},
        )

    graph.add_edge("propose_fix", "approval_gate")

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
