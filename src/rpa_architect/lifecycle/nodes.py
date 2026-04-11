"""Node functions for the lifecycle LangGraph agent."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from rpa_architect.lifecycle.state import (
    LifecycleEvent,
    LifecyclePhase,
    LifecycleState,
)

logger = logging.getLogger(__name__)


def _append_event(
    state: LifecycleState,
    event_type: str,
    detail: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append a lifecycle event to the state history."""
    state.history.append(
        LifecycleEvent(
            phase=state.phase,
            event_type=event_type,
            detail=detail,
            metadata=metadata or {},
        )
    )


async def author_node(state: LifecycleState) -> LifecycleState:
    """Author automation from PDD/IR/NL using the existing codegen pipeline."""
    state.phase = LifecyclePhase.AUTHORING
    _append_event(state, "authoring_started", f"Source type: {state.request.source_type}")

    try:
        if state.request.source_type == "pdd":
            from rpa_architect.mcp_server.tools import generate_from_pdd

            result = await generate_from_pdd(
                state.request.source,
                state.project_dir or "output",
            )
        elif state.request.source_type == "ir":
            from rpa_architect.mcp_server.tools import generate_from_ir

            result = await generate_from_ir(state.request.source, state.project_dir or "output")
        else:
            # Natural language: parse as PDD text first
            from rpa_architect.mcp_server.tools import generate_from_pdd

            result = await generate_from_pdd(
                state.request.source,
                state.project_dir or "output",
            )

        state.generation_result = result
        if result.get("success"):
            state.ir = result.get("ir", state.ir)
            state.project_dir = result.get("output_dir", state.project_dir)
            state.errors = []
            _append_event(
                state,
                "authoring_complete",
                f"Generated {len(result.get('files', []))} files",
                {"files": result.get("files", [])},
            )
        else:
            state.errors = result.get("errors", ["Generation failed"])
            _append_event(state, "authoring_failed", "; ".join(state.errors))

    except Exception as exc:
        logger.exception("Authoring failed")
        state.errors = [f"Authoring error: {exc}"]
        _append_event(state, "authoring_error", str(exc))

    return state


async def validate_gate_node(state: LifecycleState) -> LifecycleState:
    """Validate the generated project (Roslyn + XAML lint + structure + tests)."""
    state.phase = LifecyclePhase.VALIDATING
    _append_event(state, "validation_started", f"Project: {state.project_dir}")

    try:
        from rpa_architect.mcp_server.tools import validate_project

        result = await validate_project(state.project_dir)

        if result.get("valid"):
            state.errors = []
            _append_event(state, "validation_passed", "All checks passed")
        else:
            state.errors = result.get("issues", ["Validation failed"])
            state.iteration += 1
            _append_event(
                state,
                "validation_failed",
                f"Iteration {state.iteration}/{state.max_iterations}: {len(state.errors)} issues",
            )

    except Exception as exc:
        logger.exception("Validation failed")
        state.errors = [f"Validation error: {exc}"]
        state.iteration += 1

    return state


async def deploy_node(state: LifecycleState) -> LifecycleState:
    """Deploy the validated project to UiPath Orchestrator."""
    state.phase = LifecyclePhase.DEPLOYING
    _append_event(state, "deployment_started", f"Target: {state.request.deploy_target}")

    try:
        from rpa_architect.lifecycle.deployer import deploy_project

        deployment = await deploy_project(
            project_dir=state.project_dir,
            folder=state.request.deploy_target,
            ir_snapshot=state.ir,
        )

        state.deployment = deployment
        state.errors = []
        _append_event(
            state,
            "deployment_complete",
            f"Deployed {deployment.process_key} v{deployment.version} to {deployment.folder}",
        )
        logger.info("Deployed %s to %s", deployment.process_key, deployment.folder)

    except Exception as exc:
        logger.exception("Deployment failed")
        state.errors = [f"Deployment error: {exc}"]
        _append_event(state, "deployment_failed", str(exc))

    return state


async def monitor_node(state: LifecycleState) -> LifecycleState:
    """Monitor the deployed process for execution failures."""
    state.phase = LifecyclePhase.MONITORING
    _append_event(state, "monitoring_started", f"Process: {state.deployment.process_key}")

    try:
        from rpa_architect.lifecycle.monitor import collect_monitoring_report

        report = await collect_monitoring_report(
            process_key=state.deployment.process_key,
            folder=state.deployment.folder,
        )

        state.monitoring_report = report
        state.diagnosis = None
        state.fix_proposal = None
        state.approval_status = "pending"

        _append_event(
            state,
            "monitoring_complete",
            f"{report.total_jobs} jobs: {report.successful} ok, {report.faulted} faulted "
            f"({report.success_rate:.0%} success rate)",
            {"success_rate": report.success_rate, "faulted": report.faulted},
        )

    except Exception as exc:
        logger.exception("Monitoring failed")
        state.errors.append(f"Monitoring error: {exc}")
        _append_event(state, "monitoring_error", str(exc))

    return state


async def diagnose_node(state: LifecycleState) -> LifecycleState:
    """Diagnose root causes of execution failures."""
    state.phase = LifecyclePhase.DIAGNOSING
    _append_event(state, "diagnosis_started", f"{state.monitoring_report.faulted} faulted jobs")

    try:
        from rpa_architect.lifecycle.diagnosis import diagnose_failures

        diagnosis = await diagnose_failures(
            monitoring_report=state.monitoring_report,
            ir=state.ir,
            project_dir=state.project_dir,
        )

        state.diagnosis = diagnosis
        _append_event(
            state,
            "diagnosis_complete",
            f"Root cause: {diagnosis.category} ({diagnosis.confidence:.0%} confidence). "
            f"Action: {diagnosis.recommended_action}",
        )
        logger.info("Diagnosis: %s → %s", diagnosis.category, diagnosis.recommended_action)

    except Exception as exc:
        logger.exception("Diagnosis failed")
        state.errors.append(f"Diagnosis error: {exc}")
        _append_event(state, "diagnosis_error", str(exc))

    return state


async def propose_fix_node(state: LifecycleState) -> LifecycleState:
    """Generate a fix proposal based on the diagnosis."""
    _append_event(state, "fix_proposal_started", f"For: {state.diagnosis.category}")

    try:
        from rpa_architect.lifecycle.fix_proposer import generate_fix_proposal

        proposal = await generate_fix_proposal(
            diagnosis=state.diagnosis,
            project_dir=state.project_dir,
            ir=state.ir,
        )

        state.fix_proposal = proposal
        state.approval_status = "pending"
        _append_event(
            state,
            "fix_proposed",
            f"{proposal.description} ({len(proposal.changes)} changes, risk: {proposal.risk_level})",
            {"proposal_id": proposal.proposal_id},
        )

    except Exception as exc:
        logger.exception("Fix proposal failed")
        state.errors.append(f"Fix proposal error: {exc}")
        _append_event(state, "fix_proposal_error", str(exc))

    return state


async def approval_gate_node(state: LifecycleState) -> LifecycleState:
    """Route fix proposal through human approval (Action Center or auto-approve)."""
    state.phase = LifecyclePhase.AWAITING_APPROVAL

    if not state.request.require_approval_for_fixes:
        state.approval_status = "approved"
        _append_event(state, "auto_approved", "Approval not required — auto-approved")
        return state

    if state.fix_proposal and state.fix_proposal.risk_level == "low":
        state.approval_status = "approved"
        _append_event(state, "auto_approved", "Low-risk fix — auto-approved")
        return state

    try:
        from rpa_architect.platform.action_center import (
            create_review_task,
            wait_for_task_completion,
        )

        task = await create_review_task(
            title=f"Fix Proposal: {state.fix_proposal.description}",
            data={
                "proposal_id": state.fix_proposal.proposal_id,
                "risk_level": state.fix_proposal.risk_level,
                "changes": [c.model_dump() for c in state.fix_proposal.changes],
                "diagnosis": state.diagnosis.model_dump() if state.diagnosis else {},
            },
        )

        _append_event(state, "approval_requested", f"Action Center task: {task.task_id}")

        result = await wait_for_task_completion(task.task_id)
        state.approval_status = "approved" if result.status == "Completed" else "rejected"
        _append_event(state, f"approval_{state.approval_status}", f"Task {task.task_id}: {result.status}")

    except Exception as exc:
        logger.exception("Approval gate error")
        state.approval_status = "rejected"
        state.errors.append(f"Approval error: {exc}")
        _append_event(state, "approval_error", str(exc))

    return state


async def apply_fix_node(state: LifecycleState) -> LifecycleState:
    """Apply the approved fix proposal and re-enter the validation loop."""
    state.phase = LifecyclePhase.FIXING
    _append_event(state, "fix_started", f"Applying {len(state.fix_proposal.changes)} changes")

    try:
        from rpa_architect.lifecycle.fix_proposer import apply_fix

        await apply_fix(
            fix_proposal=state.fix_proposal,
            project_dir=state.project_dir,
        )

        state.iteration += 1
        state.errors = []
        _append_event(
            state,
            "fix_applied",
            f"Fix applied (iteration {state.iteration}/{state.max_iterations})",
        )

    except Exception as exc:
        logger.exception("Fix application failed")
        state.errors.append(f"Fix apply error: {exc}")
        _append_event(state, "fix_apply_error", str(exc))

    return state
