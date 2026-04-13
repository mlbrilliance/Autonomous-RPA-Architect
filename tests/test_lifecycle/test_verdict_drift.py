"""Tests for verdict-distribution drift detection added in EV2-7.

Extends the existing 3-drift-type detector with a fourth type:
``verdict_distribution_shift``. Fires when the ratio of any single
adjudication outcome (auto_approve / flag_for_review / deny) shifts
more than the threshold relative to the rolling baseline.

Also tests the schema migration on MetricsStore — the new
``verdicts_by_category`` column must be added to existing databases
on connect without losing data.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from rpa_architect.lifecycle.metrics_store import MetricsStore
from rpa_architect.lifecycle.state import MonitoringReport


def _make_report(
    *,
    process_key: str = "claims.performer",
    auto_approve: int = 45,
    flag_for_review: int = 4,
    deny: int = 1,
    recorded_at: datetime | None = None,
) -> MonitoringReport:
    total = auto_approve + flag_for_review + deny
    rep = MonitoringReport(
        process_key=process_key,
        period_start=datetime.utcnow() - timedelta(hours=1),
        period_end=recorded_at or datetime.utcnow(),
        total_jobs=total,
        successful=total,
        faulted=0,
        success_rate=1.0,
        avg_duration_seconds=30.0,
    )
    # Set through setattr since the field is new in this phase.
    rep.verdicts_by_category = {
        "auto_approve": auto_approve,
        "flag_for_review": flag_for_review,
        "deny": deny,
    }
    return rep


# ---------------------------------------------------------------------------
# Schema migration
# ---------------------------------------------------------------------------


def test_schema_migration_adds_verdicts_column_to_fresh_db(tmp_path: Path) -> None:
    db = tmp_path / "metrics.db"
    store = MetricsStore(db)
    store._get_conn()  # trigger schema init
    conn = sqlite3.connect(str(db))
    cols = [row[1] for row in conn.execute("PRAGMA table_info(monitoring_snapshots)")]
    assert "verdicts_by_category" in cols
    store.close()


def test_schema_migration_preserves_existing_data(tmp_path: Path) -> None:
    """An old-schema DB must gain the new column without losing existing rows."""
    db = tmp_path / "legacy.db"
    # Simulate a legacy-schema DB.
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE monitoring_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            process_key TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            total_jobs INTEGER NOT NULL,
            successful INTEGER NOT NULL,
            faulted INTEGER NOT NULL,
            success_rate REAL NOT NULL,
            avg_duration_seconds REAL NOT NULL,
            errors_by_type TEXT NOT NULL DEFAULT '{}'
        );
        INSERT INTO monitoring_snapshots
          (process_key, recorded_at, total_jobs, successful, faulted,
           success_rate, avg_duration_seconds, errors_by_type)
        VALUES ('legacy.proc', '2026-04-01T00:00:00', 10, 10, 0, 1.0, 5.0, '{}');
        """
    )
    conn.commit()
    conn.close()

    store = MetricsStore(db)
    store._get_conn()  # migration runs here

    check = sqlite3.connect(str(db))
    cols = [row[1] for row in check.execute("PRAGMA table_info(monitoring_snapshots)")]
    assert "verdicts_by_category" in cols
    # Legacy row still present.
    rows = check.execute(
        "SELECT process_key, total_jobs FROM monitoring_snapshots"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "legacy.proc"
    assert rows[0][1] == 10
    store.close()


# ---------------------------------------------------------------------------
# Verdict distribution drift detection
# ---------------------------------------------------------------------------


def test_verdict_distribution_stable_no_drift(tmp_path: Path) -> None:
    """Stable baseline + stable recent window → no drift."""
    db = tmp_path / "stable.db"
    store = MetricsStore(db)
    now = datetime.utcnow()

    # 10 baseline snapshots with consistent 90/8/2 distribution.
    for i in range(10):
        rep = _make_report(
            auto_approve=90,
            flag_for_review=8,
            deny=2,
            recorded_at=now - timedelta(days=14 + i),
        )
        store.record(rep)
    # 3 recent snapshots, same distribution.
    for i in range(3):
        rep = _make_report(
            auto_approve=90,
            flag_for_review=8,
            deny=2,
            recorded_at=now - timedelta(days=i),
        )
        store.record(rep)

    drift = store.detect_drift("claims.performer")
    # No success_rate or duration drift either (all equal).
    assert drift is None or drift.drift_type != "verdict_distribution_shift"
    store.close()


def test_deny_rate_shift_over_threshold_fires_drift(tmp_path: Path) -> None:
    """Baseline deny rate 2% → recent deny rate 20% → fires drift."""
    db = tmp_path / "deny_shift.db"
    store = MetricsStore(db)
    now = datetime.utcnow()

    # 10 baseline snapshots: mostly auto-approve.
    for i in range(10):
        rep = _make_report(
            auto_approve=95,
            flag_for_review=3,
            deny=2,
            recorded_at=now - timedelta(days=14 + i),
        )
        store.record(rep)

    # 5 recent snapshots: deny rate jumped.
    for i in range(5):
        rep = _make_report(
            auto_approve=70,
            flag_for_review=10,
            deny=20,
            recorded_at=now - timedelta(days=i),
        )
        store.record(rep)

    drift = store.detect_drift("claims.performer")
    assert drift is not None
    assert drift.drift_type == "verdict_distribution_shift"
    assert drift.severity in ("medium", "high")
    store.close()


def test_auto_approve_rate_drop_fires_drift(tmp_path: Path) -> None:
    """Baseline auto-approve 90% → recent 50% → fires drift."""
    db = tmp_path / "approve_drop.db"
    store = MetricsStore(db)
    now = datetime.utcnow()

    for i in range(10):
        rep = _make_report(
            auto_approve=90,
            flag_for_review=8,
            deny=2,
            recorded_at=now - timedelta(days=14 + i),
        )
        store.record(rep)
    for i in range(5):
        rep = _make_report(
            auto_approve=50,
            flag_for_review=45,
            deny=5,
            recorded_at=now - timedelta(days=i),
        )
        store.record(rep)

    drift = store.detect_drift("claims.performer")
    assert drift is not None
    assert drift.drift_type == "verdict_distribution_shift"
    store.close()


def test_verdict_distribution_requires_baseline_minimum(tmp_path: Path) -> None:
    """Only 2 baseline snapshots → can't establish baseline → no drift fired
    (avoids first-10-minute false positives)."""
    db = tmp_path / "thin_baseline.db"
    store = MetricsStore(db)
    now = datetime.utcnow()

    # Only 2 baseline snapshots.
    for i in range(2):
        rep = _make_report(
            auto_approve=90,
            flag_for_review=8,
            deny=2,
            recorded_at=now - timedelta(days=14 + i),
        )
        store.record(rep)
    # Wildly different recent window.
    rep = _make_report(auto_approve=0, flag_for_review=0, deny=100)
    store.record(rep)

    drift = store.detect_drift("claims.performer")
    assert drift is None or drift.drift_type != "verdict_distribution_shift"
    store.close()


# ---------------------------------------------------------------------------
# MonitoringReport field
# ---------------------------------------------------------------------------


def test_monitoring_report_has_verdicts_by_category_field() -> None:
    rep = MonitoringReport(
        process_key="claims.performer",
        period_start=datetime.utcnow() - timedelta(hours=1),
        period_end=datetime.utcnow(),
    )
    assert hasattr(rep, "verdicts_by_category")
    assert rep.verdicts_by_category == {}  # default empty


def test_drift_report_type_includes_verdict_distribution_shift() -> None:
    from rpa_architect.lifecycle.state import DriftReport

    # Should not raise — the Literal must include the new type.
    rep = DriftReport(
        process_key="claims.performer",
        drift_type="verdict_distribution_shift",
        severity="medium",
        baseline_value=0.9,
        current_value=0.5,
        recommendation="test",
    )
    assert rep.drift_type == "verdict_distribution_shift"
