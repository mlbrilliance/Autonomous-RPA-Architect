"""Tests for proof/run_sla_claims.py — EV2-10.

Covers:
  - Fault injection fixture matches the 5 rules
  - The tick() function invokes dispatcher then performer in sequence
  - Tick skips when previous performer job still running (BW-08)
  - Verify phase asserts drift fired + diagnosis categorised faults
  - HTML report is emitted at the end
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

FIXTURE = Path(__file__).parent.parent / "fixtures" / "claims" / "seed_claims.json"


def test_sla_script_is_importable() -> None:
    from proof import run_sla_claims  # noqa: F401


def test_sla_script_has_main_function() -> None:
    from proof import run_sla_claims

    assert hasattr(run_sla_claims, "main")
    assert callable(run_sla_claims.main)


def test_fault_injection_covers_all_five_rules() -> None:
    """The fixture must have one fault case for each of the 5 rules
    so the SLA run can verify every rule fired on a real claim."""
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    faults = data["fault_indices"]
    expected = {
        "expired_policy",       # CoverageVerificationRule
        "fraud_velocity",       # FraudVelocityRule
        "out_of_network",       # NetworkProviderRule
        "missing_docs",         # DocumentationCompletenessRule
        "amount_over_threshold",  # AmountThresholdRule
    }
    assert set(faults.keys()) == expected


def test_sla_script_has_tick_function() -> None:
    from proof.run_sla_claims import tick

    assert callable(tick)


async def test_tick_invokes_dispatcher_then_performer() -> None:
    from proof import run_sla_claims

    client = MagicMock()
    client.get_job_status = AsyncMock(return_value=MagicMock(state="Successful"))
    client.invoke_process = AsyncMock(return_value="job-id-123")
    client.list_jobs = AsyncMock(return_value=[])

    state = run_sla_claims.SlaRunState(
        dispatcher_release="disp-key",
        performer_release="perf-key",
        last_performer_job_id=None,
    )
    await run_sla_claims.tick(client, state)

    # Both processes invoked.
    assert client.invoke_process.await_count == 2
    invoked_keys = [call.args[0] for call in client.invoke_process.await_args_list]
    assert invoked_keys == ["disp-key", "perf-key"]


async def test_tick_skips_when_previous_performer_still_running() -> None:
    """BW-08: Community Cloud has 1 robot slot. If the previous Performer
    is still draining, we must skip this tick's Dispatcher call rather
    than piling up."""
    from proof import run_sla_claims

    client = MagicMock()
    running_status = MagicMock(state="Running")
    client.get_job_status = AsyncMock(return_value=running_status)
    client.invoke_process = AsyncMock(return_value="job-id")
    client.list_jobs = AsyncMock(return_value=[])

    state = run_sla_claims.SlaRunState(
        dispatcher_release="disp-key",
        performer_release="perf-key",
        last_performer_job_id="prev-perf-123",
    )
    result = await run_sla_claims.tick(client, state)

    assert result.get("skipped") is True
    assert client.invoke_process.await_count == 0


def test_sla_verify_phase_identifies_drift_in_metrics_store(tmp_path: Path) -> None:
    """After an SLA run with heavy deny distribution, the verify phase
    should detect that drift_detector flagged the anomaly."""
    from rpa_architect.lifecycle.metrics_store import MetricsStore
    from rpa_architect.lifecycle.state import MonitoringReport
    from proof.run_sla_claims import verify_drift_fired

    db = tmp_path / "metrics.db"
    store = MetricsStore(db)
    now = datetime.utcnow()

    # 10 baseline snapshots with normal distribution
    for i in range(10):
        rep = MonitoringReport(
            process_key="claims.performer",
            period_start=now - timedelta(days=14 + i, hours=1),
            period_end=now - timedelta(days=14 + i),
            total_jobs=50, successful=50, faulted=0,
            success_rate=1.0,
        )
        rep.verdicts_by_category = {"auto_approve": 45, "flag_for_review": 3, "deny": 2}
        store.record(rep)

    # Recent window with shifted distribution
    for i in range(3):
        rep = MonitoringReport(
            process_key="claims.performer",
            period_start=now - timedelta(hours=1, days=i),
            period_end=now - timedelta(days=i),
            total_jobs=50, successful=50, faulted=0,
            success_rate=1.0,
        )
        rep.verdicts_by_category = {"auto_approve": 20, "flag_for_review": 15, "deny": 15}
        store.record(rep)

    drift_fired = verify_drift_fired(store, "claims.performer")
    assert drift_fired is True
    store.close()


def test_sla_verify_phase_returns_false_when_no_drift(tmp_path: Path) -> None:
    from rpa_architect.lifecycle.metrics_store import MetricsStore
    from rpa_architect.lifecycle.state import MonitoringReport
    from proof.run_sla_claims import verify_drift_fired

    db = tmp_path / "stable.db"
    store = MetricsStore(db)
    now = datetime.utcnow()
    for i in range(10):
        rep = MonitoringReport(
            process_key="claims.performer",
            period_start=now - timedelta(days=14 + i, hours=1),
            period_end=now - timedelta(days=14 + i),
            total_jobs=50, successful=50, faulted=0,
            success_rate=1.0,
        )
        rep.verdicts_by_category = {"auto_approve": 45, "flag_for_review": 3, "deny": 2}
        store.record(rep)

    drift_fired = verify_drift_fired(store, "claims.performer")
    assert drift_fired is False
    store.close()


def test_sla_html_report_rendered_contains_distribution(tmp_path: Path) -> None:
    from proof.run_sla_claims import render_sla_html

    metrics = {
        "auto_approve": 85,
        "flag_for_review": 10,
        "deny": 5,
        "total": 100,
        "drift_fired": True,
        "diagnosis_category": "business_rule_violation",
        "p50_latency_seconds": 42.0,
        "success_rate": 0.96,
    }
    html = render_sla_html(metrics)
    assert "<html" in html
    assert "85" in html
    assert "flag_for_review" in html.lower()
    assert "42" in html
    assert "96" in html or "0.96" in html or "96.0" in html
