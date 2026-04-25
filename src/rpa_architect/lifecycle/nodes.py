"""Node functions for the lifecycle LangGraph agent."""

from __future__ import annotations

import logging
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
                state.authoring.project_dir or "output",
            )
        elif state.request.source_type == "ir":
            from rpa_architect.mcp_server.tools import generate_from_ir

            result = await generate_from_ir(
                state.request.source, state.authoring.project_dir or "output"
            )
        else:
            # Natural language: parse as PDD text first
            from rpa_architect.mcp_server.tools import generate_from_pdd

            result = await generate_from_pdd(
                state.request.source,
                state.authoring.project_dir or "output",
            )

        state.authoring.generation_result = result
        if result.get("success"):
            state.authoring.ir = result.get("ir", state.authoring.ir)
            state.authoring.project_dir = result.get("output_dir", state.authoring.project_dir)
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
    _append_event(state, "validation_started", f"Project: {state.authoring.project_dir}")

    try:
        from rpa_architect.mcp_server.tools import validate_project

        result = await validate_project(state.authoring.project_dir)

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
            project_dir=state.authoring.project_dir,
            folder=state.request.deploy_target,
            ir_snapshot=state.authoring.ir,
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

        state.monitoring.report = report
        state.monitoring.diagnosis = None
        state.fix.outcome = None
        state.fix.approval_status = "pending"

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
    _append_event(state, "diagnosis_started", f"{state.monitoring.report.faulted} faulted jobs")

    try:
        from rpa_architect.lifecycle.diagnosis import diagnose_failures

        diagnosis = await diagnose_failures(
            monitoring_report=state.monitoring.report,
            ir=state.authoring.ir,
            project_dir=state.authoring.project_dir,
        )

        state.monitoring.diagnosis = diagnosis
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


async def approval_gate_node(state: LifecycleState) -> LifecycleState:
    """Route the fix proposal carried on ``last_fix_outcome`` through approval.

    Reads the typed :class:`FixProposal` from ``state.fix.outcome.proposal``;
    falls back to ``rejected`` when no proposal is attached (e.g. the catch-all
    ran but ``fix_proposer`` raised mid-flight).
    """
    state.phase = LifecyclePhase.AWAITING_APPROVAL
    proposal = state.fix.outcome.proposal if state.fix.outcome else None

    if proposal is None:
        state.fix.approval_status = "rejected"
        _append_event(state, "approval_no_proposal", "No proposal attached to outcome")
        return state

    if not state.request.require_approval_for_fixes:
        state.fix.approval_status = "approved"
        _append_event(state, "auto_approved", "Approval not required — auto-approved")
        return state

    if proposal.risk_level == "low":
        state.fix.approval_status = "approved"
        _append_event(state, "auto_approved", "Low-risk fix — auto-approved")
        return state

    try:
        from rpa_architect.platform.action_center import (
            create_review_task,
            wait_for_task_completion,
        )

        task = await create_review_task(
            title=f"Fix Proposal: {proposal.description}",
            data={
                "proposal_id": proposal.proposal_id,
                "risk_level": proposal.risk_level,
                "changes": [c.model_dump() for c in proposal.changes],
                "diagnosis": state.monitoring.diagnosis.model_dump()
                if state.monitoring.diagnosis
                else {},
            },
        )

        _append_event(state, "approval_requested", f"Action Center task: {task.task_id}")

        result = await wait_for_task_completion(task.task_id)
        state.fix.approval_status = "approved" if result.status == "Completed" else "rejected"
        _append_event(
            state, f"approval_{state.fix.approval_status}", f"Task {task.task_id}: {result.status}"
        )

    except Exception as exc:
        logger.exception("Approval gate error")
        state.fix.approval_status = "rejected"
        state.errors.append(f"Approval error: {exc}")
        _append_event(state, "approval_error", str(exc))

    return state


async def apply_fix_node(state: LifecycleState) -> LifecycleState:
    """Apply the approved proposal carried on ``last_fix_outcome``."""
    state.phase = LifecyclePhase.FIXING
    proposal = state.fix.outcome.proposal if state.fix.outcome else None

    if proposal is None:
        state.errors.append("apply_fix: no proposal on last_fix_outcome")
        _append_event(state, "fix_apply_error", "no proposal to apply")
        return state

    _append_event(state, "fix_started", f"Applying {len(proposal.changes)} changes")

    try:
        from rpa_architect.lifecycle.fix_proposer import apply_fix

        await apply_fix(
            fix_proposal=proposal,
            project_dir=state.authoring.project_dir,
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
