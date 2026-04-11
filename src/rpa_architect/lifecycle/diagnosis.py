"""LLM-powered root cause diagnosis of execution failures."""

from __future__ import annotations

import json
import logging
from typing import Any

from rpa_architect.lifecycle.state import DiagnosisResult, MonitoringReport

logger = logging.getLogger(__name__)

_DIAGNOSIS_SYSTEM_PROMPT = """\
You are an expert UiPath RPA diagnostic agent. Analyze execution failure logs and
determine the root cause category, affected files, and recommended action.

You MUST respond with valid JSON matching this schema:
{
  "root_cause": "description of the root cause",
  "category": "selector_drift|data_schema_change|system_timeout|credential_expiry|business_rule_violation|code_bug|infrastructure|extraction_quality|unknown",
  "affected_files": ["list", "of", "affected", "files"],
  "confidence": 0.85,
  "recommended_action": "fix_code|update_selectors|update_config|escalate_to_human|retry|no_action",
  "evidence": ["log excerpt 1", "log excerpt 2"]
}

Category guidelines:
- selector_drift: UI selectors no longer match (SelectorNotFoundException, UiElement errors)
- data_schema_change: Data format/schema changed (field missing, type mismatch)
- system_timeout: Target system slow or unresponsive (TimeoutException)
- credential_expiry: Login failures, auth errors
- business_rule_violation: BusinessRuleException, validation failures
- code_bug: Logic errors, null reference, invalid operation
- infrastructure: Network, file system, Orchestrator connectivity issues
- extraction_quality: Document Understanding extraction confidence below
  threshold, validation station rejections, or wrong/missing extracted fields
  (LowConfidenceException, ValidationStationRejected, MissingExtractedField)
- unknown: Cannot determine with confidence

Recommended actions:
- fix_code: Modify workflow logic or C# code
- update_selectors: Re-harvest or manually update selectors
- update_config: Change Config.xlsx settings or Orchestrator assets
- escalate_to_human: Issue requires human judgment or investigation
- retry: Transient failure, retry may succeed
- no_action: Self-resolved or not actionable"""


async def diagnose_failures(
    monitoring_report: MonitoringReport,
    ir: dict[str, Any],
    project_dir: str,
) -> DiagnosisResult:
    """Analyze failed jobs and determine root cause.

    Args:
        monitoring_report: Aggregated monitoring data with failed job logs.
        ir: ProcessIR snapshot for context.
        project_dir: Path to the project for file inspection.

    Returns:
        DiagnosisResult with category, confidence, and recommended action.
    """
    # Build context from failed jobs
    failure_context = _build_failure_context(monitoring_report)

    # Try LLM-based diagnosis
    try:
        return await _llm_diagnose(failure_context, ir, project_dir)
    except Exception as exc:
        logger.warning("LLM diagnosis failed, falling back to heuristic: %s", exc)
        return _heuristic_diagnose(monitoring_report)


def _build_failure_context(report: MonitoringReport) -> str:
    """Build a text context from failed jobs for LLM analysis."""
    lines = [
        f"Process: {report.process_key}",
        f"Period: {report.period_start.isoformat()} to {report.period_end.isoformat()}",
        f"Total jobs: {report.total_jobs}, Faulted: {report.faulted}, "
        f"Success rate: {report.success_rate:.1%}",
        f"\nError distribution: {json.dumps(report.errors_by_type, indent=2)}",
        "\n--- Failed Job Details ---",
    ]

    for i, job in enumerate(report.failed_jobs[:10], 1):
        lines.append(f"\n[Job {i}] ID={job.job_id} State={job.state}")
        lines.append(f"  Info: {job.info[:500]}")
        if job.robot_logs:
            lines.append("  Robot logs (last 5):")
            for log_entry in job.robot_logs[-5:]:
                level = log_entry.get("Level", "")
                msg = str(log_entry.get("Message", ""))[:200]
                lines.append(f"    [{level}] {msg}")

    return "\n".join(lines)


async def _llm_diagnose(
    failure_context: str,
    ir: dict[str, Any],
    project_dir: str,
) -> DiagnosisResult:
    """Use LLM to diagnose failures."""
    from rpa_architect.utils.llm_client import LLMClient

    client = LLMClient()

    process_context = json.dumps(
        {k: ir[k] for k in ("process_name", "process_type", "description", "systems") if k in ir},
        indent=2,
    )

    user_prompt = (
        f"Analyze these UiPath automation execution failures and diagnose the root cause.\n\n"
        f"Process context:\n{process_context}\n\n"
        f"Failure data:\n{failure_context}\n\n"
        f"Respond with the JSON diagnosis."
    )

    response = await client.complete(
        system=_DIAGNOSIS_SYSTEM_PROMPT,
        prompt=user_prompt,
    )

    # Parse JSON from response
    response_text = response if isinstance(response, str) else str(response)
    # Extract JSON block if wrapped in markdown
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]

    data = json.loads(response_text.strip())
    return DiagnosisResult.model_validate(data)


_EXTRACTION_QUALITY_PATTERNS = (
    "LowConfidenceException",
    "ValidationStationRejected",
    "MissingExtractedField",
    "DocumentClassificationFailed",
    "ExtractorConfidenceBelowThreshold",
)


def _heuristic_diagnose(report: MonitoringReport) -> DiagnosisResult:
    """Fallback heuristic diagnosis based on error patterns."""
    errors = report.errors_by_type

    if any(
        any(pat in k for pat in _EXTRACTION_QUALITY_PATTERNS) for k in errors
    ):
        return DiagnosisResult(
            root_cause=(
                "Document Understanding extraction quality below the configured "
                "confidence threshold (or validation station rejection)"
            ),
            category="extraction_quality",
            confidence=0.85,
            recommended_action="escalate_to_human",
            evidence=[f"{k}: {v} occurrences" for k, v in errors.items()],
        )

    if any("SelectorNotFoundException" in k or "UiElement" in k for k in errors):
        return DiagnosisResult(
            root_cause="UI selectors no longer match target application elements",
            category="selector_drift",
            confidence=0.8,
            recommended_action="update_selectors",
            evidence=[f"{k}: {v} occurrences" for k, v in errors.items()],
        )

    if any("TimeoutException" in k for k in errors):
        return DiagnosisResult(
            root_cause="Target system timeouts during execution",
            category="system_timeout",
            confidence=0.7,
            recommended_action="retry",
            evidence=[f"{k}: {v} occurrences" for k, v in errors.items()],
        )

    if any("BusinessRuleException" in k for k in errors):
        return DiagnosisResult(
            root_cause="Business rule validation failures",
            category="business_rule_violation",
            confidence=0.75,
            recommended_action="escalate_to_human",
            evidence=[f"{k}: {v} occurrences" for k, v in errors.items()],
        )

    if any(pattern in k for k in errors for pattern in ("HttpRequestException", "IOException")):
        return DiagnosisResult(
            root_cause="Infrastructure or connectivity issues",
            category="infrastructure",
            confidence=0.6,
            recommended_action="retry",
            evidence=[f"{k}: {v} occurrences" for k, v in errors.items()],
        )

    # Default
    top_error = max(errors, key=errors.get) if errors else "Unknown"
    return DiagnosisResult(
        root_cause=f"Unclassified failure pattern: {top_error}",
        category="unknown",
        confidence=0.3,
        recommended_action="escalate_to_human",
        evidence=[f"{k}: {v} occurrences" for k, v in errors.items()],
    )
