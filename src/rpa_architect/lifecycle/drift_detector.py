"""Drift detection integrated with the lifecycle agent."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from rpa_architect.lifecycle.state import DriftReport, MonitoringReport

logger = logging.getLogger(__name__)


async def check_drift(
    process_key: str,
    monitoring_report: MonitoringReport | None = None,
    db_path: Path | str | None = None,
) -> DriftReport | None:
    """Check for behavioral drift and optionally record the latest report.

    Args:
        process_key: Process to check.
        monitoring_report: If provided, record this report before checking.
        db_path: Path to metrics SQLite database.

    Returns:
        DriftReport if drift detected, None otherwise.
    """
    from rpa_architect.lifecycle.metrics_store import MetricsStore

    store = MetricsStore(db_path)

    try:
        if monitoring_report is not None:
            store.record(monitoring_report)

        drift = store.detect_drift(process_key)

        if drift:
            logger.warning(
                "Drift detected for %s: %s (%s) — %s",
                process_key,
                drift.drift_type,
                drift.severity,
                drift.recommendation,
            )

        return drift
    finally:
        store.close()


async def get_trend_data(
    process_key: str,
    days: int = 30,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve metric trend data for dashboard display."""
    from rpa_architect.lifecycle.metrics_store import MetricsStore

    store = MetricsStore(db_path)
    try:
        return store.get_trend(process_key, days)
    finally:
        store.close()
