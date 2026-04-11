"""Dashboard data aggregation for lifecycle observability."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DashboardData(BaseModel):
    """Aggregated dashboard data for a deployed process."""

    process_key: str = Field(description="Process identifier.")
    deployment: dict[str, Any] | None = Field(default=None, description="Current deployment record.")
    current_metrics: dict[str, Any] | None = Field(default=None, description="Latest monitoring report.")
    trends: list[dict[str, Any]] = Field(default_factory=list, description="Metric trend data points.")
    drift_alerts: list[dict[str, Any]] = Field(default_factory=list, description="Active drift alerts.")
    recent_traces: list[dict[str, Any]] = Field(default_factory=list, description="Recent lifecycle traces.")
    health_status: str = Field(default="unknown", description="Overall health: healthy, degraded, critical.")


async def get_dashboard_data(
    process_key: str,
    folder: str = "Default",
    trend_days: int = 30,
    db_path: Path | str | None = None,
) -> DashboardData:
    """Aggregate data from all observability sources for a process.

    Args:
        process_key: The deployed process key.
        folder: Orchestrator folder.
        trend_days: Number of days for trend data.
        db_path: Path to metrics database.

    Returns:
        DashboardData with all available metrics and alerts.
    """
    dashboard = DashboardData(process_key=process_key)

    # Collect monitoring report
    try:
        from rpa_architect.lifecycle.monitor import collect_monitoring_report

        report = await collect_monitoring_report(process_key, folder)
        dashboard.current_metrics = report.model_dump()

        # Determine health
        if report.success_rate >= 0.95:
            dashboard.health_status = "healthy"
        elif report.success_rate >= 0.8:
            dashboard.health_status = "degraded"
        else:
            dashboard.health_status = "critical"
    except Exception as exc:
        logger.warning("Could not collect monitoring data: %s", exc)

    # Collect trend data
    try:
        from rpa_architect.lifecycle.drift_detector import get_trend_data

        dashboard.trends = await get_trend_data(process_key, trend_days, db_path)
    except Exception as exc:
        logger.warning("Could not collect trend data: %s", exc)

    # Check for drift
    try:
        from rpa_architect.lifecycle.drift_detector import check_drift

        drift = await check_drift(process_key, db_path=db_path)
        if drift:
            dashboard.drift_alerts = [drift.model_dump()]
    except Exception as exc:
        logger.warning("Could not check drift: %s", exc)

    return dashboard
