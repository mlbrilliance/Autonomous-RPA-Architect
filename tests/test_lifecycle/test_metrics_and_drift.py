"""Tests for metrics store and drift detection."""

import pytest
from datetime import datetime, timedelta

from rpa_architect.lifecycle.state import MonitoringReport, DriftReport
from rpa_architect.lifecycle.metrics_store import MetricsStore


@pytest.fixture
def metrics_store(tmp_path):
    db_path = tmp_path / "test_metrics.db"
    store = MetricsStore(db_path)
    yield store
    store.close()


def _make_report(
    process_key: str = "test_proc",
    period_end: datetime | None = None,
    success_rate: float = 0.95,
    faulted: int = 1,
    total: int = 20,
    avg_duration: float = 30.0,
    errors: dict | None = None,
) -> MonitoringReport:
    end = period_end or datetime.utcnow()
    return MonitoringReport(
        process_key=process_key,
        period_start=end - timedelta(hours=1),
        period_end=end,
        total_jobs=total,
        successful=total - faulted,
        faulted=faulted,
        success_rate=success_rate,
        avg_duration_seconds=avg_duration,
        errors_by_type=errors or {},
    )


class TestMetricsStore:
    def test_record_and_get_trend(self, metrics_store):
        now = datetime.utcnow()
        for i in range(5):
            report = _make_report(
                period_end=now - timedelta(days=i),
                success_rate=0.95 - (i * 0.05),
            )
            metrics_store.record(report)

        trend = metrics_store.get_trend("test_proc", days=30)
        assert len(trend) == 5
        assert all("success_rate" in t for t in trend)

    def test_get_trend_empty(self, metrics_store):
        trend = metrics_store.get_trend("nonexistent", days=7)
        assert trend == []

    def test_detect_drift_success_rate_decline(self, metrics_store):
        now = datetime.utcnow()

        # Baseline: high success rate (30 days ago to 7 days ago)
        for i in range(30, 7, -1):
            metrics_store.record(_make_report(
                period_end=now - timedelta(days=i),
                success_rate=0.95,
            ))

        # Recent: low success rate (last 7 days)
        for i in range(7, 0, -1):
            metrics_store.record(_make_report(
                period_end=now - timedelta(days=i),
                success_rate=0.60,
            ))

        drift = metrics_store.detect_drift("test_proc")
        assert drift is not None
        assert drift.drift_type == "success_rate_decline"
        assert drift.severity in ("medium", "high")

    def test_detect_drift_no_drift(self, metrics_store):
        now = datetime.utcnow()
        for i in range(30, 0, -1):
            metrics_store.record(_make_report(
                period_end=now - timedelta(days=i),
                success_rate=0.95,
            ))

        drift = metrics_store.detect_drift("test_proc")
        assert drift is None

    def test_detect_drift_duration_increase(self, metrics_store):
        now = datetime.utcnow()

        # Baseline: fast
        for i in range(30, 7, -1):
            metrics_store.record(_make_report(
                period_end=now - timedelta(days=i),
                avg_duration=30.0,
            ))

        # Recent: very slow
        for i in range(7, 0, -1):
            metrics_store.record(_make_report(
                period_end=now - timedelta(days=i),
                avg_duration=120.0,
            ))

        drift = metrics_store.detect_drift("test_proc")
        assert drift is not None
        assert drift.drift_type == "duration_increase"

    def test_detect_drift_new_error_type(self, metrics_store):
        now = datetime.utcnow()

        # Baseline: known errors (days 30 to 8, safely outside 7-day window)
        for i in range(30, 8, -1):
            metrics_store.record(_make_report(
                period_end=now - timedelta(days=i),
                errors={"TimeoutException": 1},
            ))

        # Recent: new error type (days 5 to 1, safely inside 7-day window)
        for i in range(5, 0, -1):
            metrics_store.record(_make_report(
                period_end=now - timedelta(days=i),
                errors={"TimeoutException": 1, "SelectorNotFoundException": 3},
            ))

        drift = metrics_store.detect_drift("test_proc")
        assert drift is not None
        assert drift.drift_type == "new_error_type"

    def test_insufficient_data_returns_none(self, metrics_store):
        now = datetime.utcnow()
        # Only 1 data point — not enough
        metrics_store.record(_make_report(period_end=now))
        drift = metrics_store.detect_drift("test_proc")
        assert drift is None
