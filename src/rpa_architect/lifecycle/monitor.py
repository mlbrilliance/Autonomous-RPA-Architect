"""Execution monitoring: poll Orchestrator for job status and logs."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from rpa_architect.lifecycle.state import ExecutionLog, MonitoringReport

logger = logging.getLogger(__name__)


async def collect_monitoring_report(
    process_key: str,
    folder: str = "Default",
    lookback_hours: int = 24,
) -> MonitoringReport:
    """Collect execution metrics from UiPath Orchestrator.

    Args:
        process_key: The deployed process/release key.
        folder: Orchestrator folder.
        lookback_hours: How far back to look for jobs.

    Returns:
        MonitoringReport with aggregated metrics and failed job details.
    """
    from rpa_architect.config import load_config
    from rpa_architect.platform.sdk_client import UiPathClient

    cfg = load_config()
    cid = cfg.uipath.client_id
    csec = cfg.uipath.client_secret
    if not cid or not csec:
        raise RuntimeError(
            "UiPath OAuth credentials required for monitoring. "
            "Set UIPATH_CLIENT_ID and UIPATH_CLIENT_SECRET."
        )

    client = UiPathClient(
        url=cfg.uipath.url,
        tenant_id=cfg.uipath.tenant_id,
        client_id=cid.get_secret_value(),
        client_secret=csec.get_secret_value(),
        folder=folder,
    )

    period_end = datetime.utcnow()
    period_start = period_end - timedelta(hours=lookback_hours)

    try:
        jobs = await client.list_jobs(
            process_key=process_key,
            since=period_start,
            states=["Successful", "Faulted", "Stopped"],
        )

        execution_logs = _parse_jobs(jobs)
        failed = [log for log in execution_logs if log.state in ("Faulted", "Stopped")]

        # Fetch robot logs for failed jobs
        for fail in failed:
            try:
                robot_logs = await client.get_robot_logs(fail.job_id)
                fail.robot_logs = robot_logs
            except Exception as exc:
                logger.warning("Could not fetch robot logs for job %s: %s", fail.job_id, exc)

        total = len(execution_logs)
        successful = sum(1 for log in execution_logs if log.state == "Successful")
        faulted = len(failed)

        durations = [
            (log.ended_at - log.started_at).total_seconds()
            for log in execution_logs
            if log.ended_at
        ]
        avg_duration = sum(durations) / len(durations) if durations else 0.0

        errors_by_type: dict[str, int] = {}
        for fail in failed:
            error_key = _extract_error_type(fail.info)
            errors_by_type[error_key] = errors_by_type.get(error_key, 0) + 1

        return MonitoringReport(
            process_key=process_key,
            period_start=period_start,
            period_end=period_end,
            total_jobs=total,
            successful=successful,
            faulted=faulted,
            success_rate=successful / total if total > 0 else 1.0,
            avg_duration_seconds=avg_duration,
            failed_jobs=failed,
            errors_by_type=errors_by_type,
        )
    finally:
        await client.close()


def _parse_jobs(jobs: list[dict[str, Any]]) -> list[ExecutionLog]:
    """Parse OData job records into ExecutionLog models."""
    logs = []
    for job in jobs:
        try:
            started = datetime.fromisoformat(job.get("StartTime", "").replace("Z", "+00:00"))
            ended_raw = job.get("EndTime")
            ended = datetime.fromisoformat(ended_raw.replace("Z", "+00:00")) if ended_raw else None
        except (ValueError, AttributeError):
            started = datetime.utcnow()
            ended = None

        logs.append(
            ExecutionLog(
                job_id=str(job.get("Id", job.get("Key", ""))),
                state=str(job.get("State", "Unknown")),
                started_at=started,
                ended_at=ended,
                info=str(job.get("Info", "")),
            )
        )
    return logs


def _extract_error_type(info: str) -> str:
    """Extract a normalized error type key from a job info string."""
    if not info:
        return "Unknown"
    # Common UiPath error patterns
    for pattern in [
        "SelectorNotFoundException",
        "UiElement",
        "TimeoutException",
        "BusinessRuleException",
        "System.Exception",
        "InvalidOperationException",
        "IOException",
        "HttpRequestException",
    ]:
        if pattern in info:
            return pattern
    # Truncate to first line, max 80 chars
    first_line = info.split("\n")[0][:80]
    return first_line or "Unknown"
