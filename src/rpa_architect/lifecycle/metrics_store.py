"""SQLite-backed metrics store for drift detection and trend analysis."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from rpa_architect.lifecycle.state import DriftReport, MonitoringReport

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS monitoring_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    process_key TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    total_jobs INTEGER NOT NULL,
    successful INTEGER NOT NULL,
    faulted INTEGER NOT NULL,
    success_rate REAL NOT NULL,
    avg_duration_seconds REAL NOT NULL,
    errors_by_type TEXT NOT NULL DEFAULT '{}',
    verdicts_by_category TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_snapshots_process_time
    ON monitoring_snapshots(process_key, recorded_at);
"""


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Add columns that weren't present in earlier schema versions.

    Non-destructive — existing rows are preserved. Runs on every connect
    so legacy DBs upgrade transparently the first time a v0.6 build opens
    them.
    """
    existing = {row[1] for row in conn.execute("PRAGMA table_info(monitoring_snapshots)")}
    if "verdicts_by_category" not in existing:
        conn.execute(
            "ALTER TABLE monitoring_snapshots "
            "ADD COLUMN verdicts_by_category TEXT NOT NULL DEFAULT '{}'"
        )
        conn.commit()


class MetricsStore:
    """Lightweight SQLite store for execution metrics and drift detection."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            db_path = Path.home() / ".rpa_architect" / "metrics.db"
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(_SCHEMA)
            _migrate_schema(self._conn)
        return self._conn

    def record(self, report: MonitoringReport) -> None:
        """Store a monitoring snapshot."""
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO monitoring_snapshots
               (process_key, recorded_at, total_jobs, successful, faulted,
                success_rate, avg_duration_seconds, errors_by_type,
                verdicts_by_category)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                report.process_key,
                report.period_end.isoformat(),
                report.total_jobs,
                report.successful,
                report.faulted,
                report.success_rate,
                report.avg_duration_seconds,
                json.dumps(report.errors_by_type),
                json.dumps(getattr(report, "verdicts_by_category", {}) or {}),
            ),
        )
        conn.commit()
        logger.debug("Recorded metrics for %s at %s", report.process_key, report.period_end)

    def get_trend(
        self,
        process_key: str,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Get metric trend data for a process over the last N days."""
        conn = self._get_conn()
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        rows = conn.execute(
            """SELECT recorded_at, success_rate, avg_duration_seconds, faulted, total_jobs
               FROM monitoring_snapshots
               WHERE process_key = ? AND recorded_at >= ?
               ORDER BY recorded_at ASC""",
            (process_key, since),
        ).fetchall()

        return [
            {
                "recorded_at": row["recorded_at"],
                "success_rate": row["success_rate"],
                "avg_duration_seconds": row["avg_duration_seconds"],
                "faulted": row["faulted"],
                "total_jobs": row["total_jobs"],
            }
            for row in rows
        ]

    @staticmethod
    def _avg_distribution(rows: list[sqlite3.Row]) -> dict[str, float]:
        """Return the per-category ratio averaged across the given rows.

        Rows must include ``verdicts_by_category``. Categories with zero
        grand-total return an empty dict so callers can detect "no data".
        """
        totals = {"auto_approve": 0, "flag_for_review": 0, "deny": 0}
        grand_total = 0
        for row in rows:
            try:
                dist = json.loads(row["verdicts_by_category"] or "{}")
            except (json.JSONDecodeError, TypeError):
                continue
            for k in totals:
                v = int(dist.get(k, 0))
                totals[k] += v
                grand_total += v
        if grand_total == 0:
            return {}
        return {k: v / grand_total for k, v in totals.items()}

    def detect_drift(
        self,
        process_key: str,
        window_days: int = 7,
        baseline_days: int = 30,
        success_rate_threshold: float = 0.1,
        duration_ratio_threshold: float = 2.0,
        verdict_distribution_threshold: float = 0.10,
    ) -> DriftReport | None:
        """Detect behavioral drift by comparing recent window to historical baseline.

        Args:
            process_key: Process to check.
            window_days: Recent window size for current metrics.
            baseline_days: Historical window for baseline.
            success_rate_threshold: Min decline in success rate to flag drift.
            duration_ratio_threshold: Current/baseline duration ratio to flag.

        Returns:
            DriftReport if drift detected, None otherwise.
        """
        conn = self._get_conn()
        now = datetime.utcnow()
        window_start = (now - timedelta(days=window_days)).isoformat()
        baseline_start = (now - timedelta(days=baseline_days)).isoformat()

        # Baseline metrics (full period, excluding recent window)
        baseline = conn.execute(
            """SELECT AVG(success_rate) as avg_sr, AVG(avg_duration_seconds) as avg_dur,
                      COUNT(*) as cnt
               FROM monitoring_snapshots
               WHERE process_key = ? AND recorded_at >= ? AND recorded_at < ?""",
            (process_key, baseline_start, window_start),
        ).fetchone()

        # Recent window metrics
        recent = conn.execute(
            """SELECT AVG(success_rate) as avg_sr, AVG(avg_duration_seconds) as avg_dur,
                      COUNT(*) as cnt
               FROM monitoring_snapshots
               WHERE process_key = ? AND recorded_at >= ?""",
            (process_key, window_start),
        ).fetchone()

        if not baseline or not recent or baseline["cnt"] < 3 or recent["cnt"] < 1:
            return None

        baseline_sr = baseline["avg_sr"]
        current_sr = recent["avg_sr"]
        baseline_dur = baseline["avg_dur"]
        current_dur = recent["avg_dur"]

        # Check success rate decline
        if baseline_sr - current_sr > success_rate_threshold:
            severity = "high" if baseline_sr - current_sr > 0.3 else "medium" if baseline_sr - current_sr > 0.15 else "low"
            return DriftReport(
                process_key=process_key,
                drift_type="success_rate_decline",
                severity=severity,
                baseline_value=baseline_sr,
                current_value=current_sr,
                recommendation=f"Success rate dropped from {baseline_sr:.1%} to {current_sr:.1%}. "
                f"Investigate recent failures and consider re-diagnosis.",
            )

        # Check duration increase
        if baseline_dur > 0 and current_dur / baseline_dur > duration_ratio_threshold:
            ratio = current_dur / baseline_dur
            severity = "high" if ratio > 3.0 else "medium"
            return DriftReport(
                process_key=process_key,
                drift_type="duration_increase",
                severity=severity,
                baseline_value=baseline_dur,
                current_value=current_dur,
                recommendation=f"Average duration increased {ratio:.1f}x (from {baseline_dur:.0f}s to {current_dur:.0f}s). "
                f"Check for system slowdowns or new processing bottlenecks.",
            )

        # Check verdict-distribution shift (EV2-7 — for claims factory).
        # Only fires when both baseline and recent windows have enough
        # snapshots with verdict data (avoids first-run false positives).
        baseline_rows = conn.execute(
            """SELECT verdicts_by_category FROM monitoring_snapshots
               WHERE process_key = ? AND recorded_at >= ? AND recorded_at < ?""",
            (process_key, baseline_start, window_start),
        ).fetchall()
        recent_rows = conn.execute(
            """SELECT verdicts_by_category FROM monitoring_snapshots
               WHERE process_key = ? AND recorded_at >= ?""",
            (process_key, window_start),
        ).fetchall()

        if len(baseline_rows) >= 5 and len(recent_rows) >= 1:
            baseline_dist = self._avg_distribution(baseline_rows)
            current_dist = self._avg_distribution(recent_rows)
            if baseline_dist and current_dist:
                for category in ("auto_approve", "flag_for_review", "deny"):
                    delta = current_dist[category] - baseline_dist[category]
                    if abs(delta) > verdict_distribution_threshold:
                        severity = (
                            "high" if abs(delta) > 0.25
                            else "medium" if abs(delta) > 0.15
                            else "low"
                        )
                        return DriftReport(
                            process_key=process_key,
                            drift_type="verdict_distribution_shift",
                            severity=severity,
                            baseline_value=baseline_dist[category],
                            current_value=current_dist[category],
                            recommendation=(
                                f"Verdict '{category}' rate shifted from "
                                f"{baseline_dist[category]:.1%} to "
                                f"{current_dist[category]:.1%} "
                                f"(delta {delta:+.1%}). "
                                "Investigate rule logic or upstream data changes."
                            ),
                        )

        # Check for new error types
        recent_errors = conn.execute(
            """SELECT errors_by_type FROM monitoring_snapshots
               WHERE process_key = ? AND recorded_at >= ?""",
            (process_key, window_start),
        ).fetchall()

        baseline_errors = conn.execute(
            """SELECT errors_by_type FROM monitoring_snapshots
               WHERE process_key = ? AND recorded_at >= ? AND recorded_at < ?""",
            (process_key, baseline_start, window_start),
        ).fetchall()

        recent_types = set()
        for row in recent_errors:
            recent_types.update(json.loads(row["errors_by_type"]).keys())

        baseline_types = set()
        for row in baseline_errors:
            baseline_types.update(json.loads(row["errors_by_type"]).keys())

        new_types = recent_types - baseline_types - {"Unknown"}
        if new_types:
            return DriftReport(
                process_key=process_key,
                drift_type="new_error_type",
                severity="medium",
                baseline_value=0.0,
                current_value=float(len(new_types)),
                recommendation=f"New error types detected: {', '.join(new_types)}. "
                f"These were not present in the baseline period.",
            )

        return None

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
