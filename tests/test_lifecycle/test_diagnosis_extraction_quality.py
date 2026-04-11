"""Tests for the new ``extraction_quality`` diagnosis category (Phase G)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rpa_architect.lifecycle.diagnosis import _heuristic_diagnose
from rpa_architect.lifecycle.state import ExecutionLog, MonitoringReport


def _report_with_errors(errors: dict[str, int]) -> MonitoringReport:
    now = datetime.now(timezone.utc)
    return MonitoringReport(
        process_key="OdooInvoiceProcessing",
        period_start=now,
        period_end=now,
        total_jobs=10,
        successful=7,
        faulted=3,
        success_rate=0.7,
        errors_by_type=errors,
        failed_jobs=[
            ExecutionLog(
                job_id="j1",
                state="Faulted",
                started_at=now,
                info="bad invoice",
            ),
        ],
    )


def test_low_confidence_exception_triggers_extraction_quality() -> None:
    report = _report_with_errors({"LowConfidenceException": 3})
    diagnosis = _heuristic_diagnose(report)
    assert diagnosis.category == "extraction_quality"
    assert diagnosis.recommended_action == "escalate_to_human"
    assert diagnosis.confidence > 0.5


def test_validation_station_rejected_triggers_extraction_quality() -> None:
    report = _report_with_errors({"ValidationStationRejected": 5})
    diagnosis = _heuristic_diagnose(report)
    assert diagnosis.category == "extraction_quality"


def test_missing_extracted_field_triggers_extraction_quality() -> None:
    report = _report_with_errors({"MissingExtractedField:VendorName": 2})
    diagnosis = _heuristic_diagnose(report)
    assert diagnosis.category == "extraction_quality"


def test_extraction_quality_takes_precedence_over_unknown() -> None:
    """When both extraction errors and other generic errors exist,
    extraction_quality is preferred because it's actionable."""
    report = _report_with_errors(
        {"LowConfidenceException": 1, "RandomOtherError": 5}
    )
    diagnosis = _heuristic_diagnose(report)
    assert diagnosis.category == "extraction_quality"


def test_non_extraction_error_does_not_trigger_category() -> None:
    report = _report_with_errors({"SelectorNotFoundException": 1})
    diagnosis = _heuristic_diagnose(report)
    assert diagnosis.category == "selector_drift"


def test_extraction_quality_in_valid_categories() -> None:
    """Sanity: the new category must be a valid Literal value."""
    from rpa_architect.lifecycle.state import DiagnosisResult

    DiagnosisResult(
        root_cause="test",
        category="extraction_quality",
        confidence=0.9,
        recommended_action="escalate_to_human",
        evidence=["evidence-1"],
    )
