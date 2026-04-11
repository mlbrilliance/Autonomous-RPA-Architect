"""Tests for diagnosis heuristics and error extraction."""

import pytest
from datetime import datetime, timedelta

from rpa_architect.lifecycle.state import MonitoringReport
from rpa_architect.lifecycle.diagnosis import _heuristic_diagnose
from rpa_architect.lifecycle.monitor import _extract_error_type


def _make_report(errors_by_type: dict[str, int]) -> MonitoringReport:
    return MonitoringReport(
        process_key="test",
        period_start=datetime.utcnow() - timedelta(hours=1),
        period_end=datetime.utcnow(),
        total_jobs=10,
        successful=5,
        faulted=5,
        success_rate=0.5,
        errors_by_type=errors_by_type,
    )


class TestHeuristicDiagnose:
    def test_selector_drift(self):
        report = _make_report({"SelectorNotFoundException": 5})
        result = _heuristic_diagnose(report)
        assert result.category == "selector_drift"
        assert result.recommended_action == "update_selectors"

    def test_selector_drift_ui_element(self):
        report = _make_report({"UiElement not found": 3})
        result = _heuristic_diagnose(report)
        assert result.category == "selector_drift"

    def test_system_timeout(self):
        report = _make_report({"TimeoutException": 4})
        result = _heuristic_diagnose(report)
        assert result.category == "system_timeout"
        assert result.recommended_action == "retry"

    def test_business_rule_violation(self):
        report = _make_report({"BusinessRuleException": 3})
        result = _heuristic_diagnose(report)
        assert result.category == "business_rule_violation"
        assert result.recommended_action == "escalate_to_human"

    def test_infrastructure(self):
        report = _make_report({"HttpRequestException": 2})
        result = _heuristic_diagnose(report)
        assert result.category == "infrastructure"

    def test_infrastructure_io(self):
        report = _make_report({"IOException": 1})
        result = _heuristic_diagnose(report)
        assert result.category == "infrastructure"

    def test_unknown(self):
        report = _make_report({"SomeRareError": 1})
        result = _heuristic_diagnose(report)
        assert result.category == "unknown"
        assert result.recommended_action == "escalate_to_human"

    def test_empty_errors(self):
        report = _make_report({})
        result = _heuristic_diagnose(report)
        assert result.category == "unknown"

    def test_confidence_values(self):
        report = _make_report({"SelectorNotFoundException": 5})
        result = _heuristic_diagnose(report)
        assert 0.0 <= result.confidence <= 1.0


class TestExtractErrorType:
    def test_selector_not_found(self):
        assert _extract_error_type("SelectorNotFoundException: element not found") == "SelectorNotFoundException"

    def test_timeout(self):
        assert _extract_error_type("TimeoutException after 30s") == "TimeoutException"

    def test_business_rule(self):
        assert _extract_error_type("BusinessRuleException: invalid amount") == "BusinessRuleException"

    def test_http_error(self):
        assert _extract_error_type("HttpRequestException: 503 Service Unavailable") == "HttpRequestException"

    def test_generic_error(self):
        result = _extract_error_type("Some completely unknown error message")
        assert result == "Some completely unknown error message"

    def test_empty(self):
        assert _extract_error_type("") == "Unknown"

    def test_multiline_truncated(self):
        long_msg = "First line error\nSecond line\nThird line"
        result = _extract_error_type(long_msg)
        assert "\n" not in result
