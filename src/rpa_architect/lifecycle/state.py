"""Pydantic v2 models for the autonomous lifecycle agent."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class LifecyclePhase(str, Enum):
    """Phases of the automation lifecycle."""

    AUTHORING = "authoring"
    VALIDATING = "validating"
    DEPLOYING = "deploying"
    MONITORING = "monitoring"
    DIAGNOSING = "diagnosing"
    FIXING = "fixing"
    AWAITING_APPROVAL = "awaiting_approval"


class LifecycleRequest(BaseModel):
    """Input request to the lifecycle agent."""

    source: str = Field(description="PDD path, IR JSON string, or natural language description.")
    source_type: Literal["pdd", "ir", "natural_language"] = Field(
        description="Type of the input source.",
    )
    deploy_target: str = Field(
        default="Default",
        description="UiPath Orchestrator folder for deployment.",
    )
    auto_monitor: bool = Field(
        default=True,
        description="Enable automatic monitoring after deployment.",
    )
    require_approval_for_fixes: bool = Field(
        default=True,
        description="Require human approval before applying fixes.",
    )


class DeploymentRecord(BaseModel):
    """Record of a deployed automation package."""

    process_key: str = Field(description="UiPath process/release key.")
    release_key: str = Field(description="UiPath release key.")
    package_id: str = Field(description="Published package identifier.")
    folder: str = Field(description="Orchestrator folder where deployed.")
    deployed_at: datetime = Field(default_factory=datetime.utcnow, description="Deployment timestamp.")
    ir_snapshot: dict[str, Any] = Field(default_factory=dict, description="IR snapshot at deploy time.")
    version: str = Field(default="1.0.0", description="Package version.")


class ExecutionLog(BaseModel):
    """A single UiPath job execution record."""

    job_id: str = Field(description="UiPath job identifier.")
    state: str = Field(description="Job state: Successful, Faulted, Stopped, etc.")
    started_at: datetime = Field(description="Job start timestamp.")
    ended_at: datetime | None = Field(default=None, description="Job end timestamp.")
    info: str = Field(default="", description="Job info or error message.")
    robot_logs: list[dict[str, Any]] = Field(default_factory=list, description="Robot execution log entries.")


class MonitoringReport(BaseModel):
    """Aggregated monitoring report for a deployed process."""

    process_key: str = Field(description="Monitored process key.")
    period_start: datetime = Field(description="Start of monitoring window.")
    period_end: datetime = Field(description="End of monitoring window.")
    total_jobs: int = Field(default=0, description="Total jobs in period.")
    successful: int = Field(default=0, description="Successful job count.")
    faulted: int = Field(default=0, description="Faulted job count.")
    success_rate: float = Field(default=1.0, ge=0.0, le=1.0, description="Success rate (0.0-1.0).")
    avg_duration_seconds: float = Field(default=0.0, ge=0.0, description="Average job duration.")
    failed_jobs: list[ExecutionLog] = Field(default_factory=list, description="Failed job details.")
    errors_by_type: dict[str, int] = Field(default_factory=dict, description="Error type distribution.")
    verdicts_by_category: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "Verdict counts by category (auto_approve / flag_for_review / "
            "deny) for categorical drift detection. Populated by the "
            "claims Performer via RobotLogs parsing."
        ),
    )


class DiagnosisResult(BaseModel):
    """Root cause analysis of execution failures."""

    root_cause: str = Field(description="Root cause description.")
    category: Literal[
        "selector_drift",
        "data_schema_change",
        "system_timeout",
        "credential_expiry",
        "business_rule_violation",
        "code_bug",
        "infrastructure",
        "extraction_quality",
        "unknown",
    ] = Field(description="Root cause classification.")
    affected_files: list[str] = Field(default_factory=list, description="Files affected by the issue.")
    confidence: float = Field(ge=0.0, le=1.0, description="Diagnosis confidence (0.0-1.0).")
    recommended_action: Literal[
        "fix_code",
        "update_selectors",
        "update_config",
        "escalate_to_human",
        "retry",
        "no_action",
    ] = Field(description="Recommended remediation action.")
    evidence: list[str] = Field(default_factory=list, description="Supporting log excerpts.")


class ProposedChange(BaseModel):
    """A single code or configuration change."""

    file_path: str = Field(description="Relative path within the project.")
    change_type: Literal["modify", "add", "delete", "config_update"] = Field(
        description="Type of change.",
    )
    description: str = Field(description="Human-readable change description.")
    before: str | None = Field(default=None, description="Original content.")
    after: str | None = Field(default=None, description="Replacement content.")


class FixProposal(BaseModel):
    """A proposed set of changes to fix diagnosed issues."""

    proposal_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12], description="Unique proposal ID.")
    diagnosis_ref: str = Field(default="", description="Category reference from DiagnosisResult.")
    description: str = Field(description="Summary of the proposed fix.")
    changes: list[ProposedChange] = Field(default_factory=list, description="Ordered changes to apply.")
    risk_level: Literal["low", "medium", "high"] = Field(description="Assessed risk level.")
    requires_redeployment: bool = Field(default=True, description="Whether fix requires redeployment.")
    test_plan: list[str] = Field(default_factory=list, description="Validation test cases.")


class DriftReport(BaseModel):
    """Report of behavioral drift in a deployed process."""

    process_key: str = Field(description="Process exhibiting drift.")
    detected_at: datetime = Field(default_factory=datetime.utcnow, description="Detection timestamp.")
    drift_type: Literal[
        "success_rate_decline",
        "duration_increase",
        "new_error_type",
        "throughput_decline",
        "verdict_distribution_shift",
    ] = Field(description="Type of drift detected.")
    severity: Literal["low", "medium", "high"] = Field(description="Drift severity.")
    baseline_value: float = Field(description="Historical baseline metric.")
    current_value: float = Field(description="Current observed metric.")
    recommendation: str = Field(description="Recommended action.")


class FailureBundle(BaseModel):
    """Everything the swarm needs about one faulted job.

    Composed by ``lifecycle.swarm.failure_bundle.FailureBundleFetcher`` from
    three Orchestrator endpoints (Jobs(id), RobotLogs, DownloadPackage) plus
    any artifact URLs returned in the job record.
    """

    job_id: str = Field(description="UiPath job key.")
    process_key: str = Field(description="Release / process name.")
    release_key: str = Field(default="", description="Release key (distinct from process_key).")
    state: str = Field(description="Job state: Faulted, Stopped, etc.")
    exception_message: str = Field(default="", description="Top-level exception message from Job.Info.")
    exception_type: str = Field(
        default="",
        description=(
            "Heuristically parsed exception class name — e.g. "
            "SelectorNotFoundException, NullReferenceException, TimeoutException."
        ),
    )
    started_at: datetime | None = Field(default=None, description="Job start timestamp.")
    ended_at: datetime | None = Field(default=None, description="Job end timestamp.")
    robot_logs: list[dict[str, Any]] = Field(
        default_factory=list, description="Raw RobotLog OData records for this job."
    )
    xaml_files: dict[str, str] = Field(
        default_factory=dict,
        description="Relative-path → XAML content, extracted from the deployed .nupkg.",
    )
    screenshot_paths: list[str] = Field(
        default_factory=list,
        description="Orchestrator storage paths to screenshot artifacts, if any.",
    )
    folder: str = Field(default="Default", description="Orchestrator folder name.")


class XamlPatch(BaseModel):
    """A single in-place edit to a XAML file in a FailureBundle."""

    file_path: str = Field(description="Relative path within the deployed package (e.g. Main.xaml).")
    target_xpath: str = Field(description="lxml-style xpath of the element to edit.")
    attribute: str = Field(description="Attribute name being rewritten (e.g. Selector).")
    old_value: str = Field(description="Value before patching.")
    new_value: str = Field(description="Value after patching.")
    rationale: str = Field(default="", description="Specialist's reasoning for the change.")


class FixCandidate(BaseModel):
    """One specialist's proposed repair for a FailureBundle."""

    specialist: str = Field(description="Name of the specialist agent (selector_repair, null, timing, business_rule).")
    confidence: float = Field(ge=0.0, le=1.0, description="Specialist's self-assessed confidence.")
    diagnosis_category: str = Field(description="DiagnosisResult.category value.")
    patches: list[XamlPatch] = Field(default_factory=list, description="XAML edits this candidate proposes.")
    reasoning: str = Field(default="", description="Human-readable justification.")
    patched_xaml: dict[str, str] = Field(
        default_factory=dict,
        description="Path → patched XAML content, for downstream compilation + staging.",
    )


class StagingResult(BaseModel):
    """Outcome of running a FixCandidate against the staging folder."""

    candidate_specialist: str = Field(description="Specialist name whose patch was validated.")
    success: bool = Field(description="Did the patched job complete successfully?")
    job_id: str = Field(default="", description="Staging job key.")
    duration_seconds: float = Field(default=0.0, description="Staging run wall-clock.")
    message: str = Field(default="", description="Success message or failure excerpt.")
    release_key: str = Field(default="", description="Staging release key used.")


class LifecycleEvent(BaseModel):
    """An event in the lifecycle history."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    phase: LifecyclePhase = Field(description="Phase when event occurred.")
    event_type: str = Field(description="Event type identifier.")
    detail: str = Field(description="Event detail message.")
    metadata: dict[str, Any] = Field(default_factory=dict)


class LifecycleState(BaseModel):
    """Shared state for the lifecycle LangGraph agent."""

    request: LifecycleRequest
    ir: dict[str, Any] = Field(default_factory=dict)
    generation_result: dict[str, Any] = Field(default_factory=dict)
    project_dir: str = ""
    deployment: DeploymentRecord | None = None
    monitoring_report: MonitoringReport | None = None
    diagnosis: DiagnosisResult | None = None
    fix_proposal: FixProposal | None = None
    drift_report: DriftReport | None = None
    approval_status: Literal["pending", "approved", "rejected"] = "pending"
    phase: LifecyclePhase = LifecyclePhase.AUTHORING
    iteration: int = 0
    max_iterations: int = 3
    errors: list[str] = Field(default_factory=list)
    history: list[LifecycleEvent] = Field(default_factory=list)
