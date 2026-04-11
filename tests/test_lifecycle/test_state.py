"""Tests for lifecycle state models."""

import pytest
from datetime import datetime

from rpa_architect.lifecycle.state import (
    DeploymentRecord,
    DiagnosisResult,
    DriftReport,
    ExecutionLog,
    FixProposal,
    LifecycleEvent,
    LifecyclePhase,
    LifecycleRequest,
    LifecycleState,
    MonitoringReport,
    ProposedChange,
)


class TestLifecyclePhase:
    def test_enum_values(self):
        assert LifecyclePhase.AUTHORING == "authoring"
        assert LifecyclePhase.MONITORING == "monitoring"
        assert LifecyclePhase.DIAGNOSING == "diagnosing"
        assert LifecyclePhase.FIXING == "fixing"
        assert LifecyclePhase.AWAITING_APPROVAL == "awaiting_approval"

    def test_all_phases_present(self):
        assert len(LifecyclePhase) == 7


class TestLifecycleRequest:
    def test_defaults(self):
        req = LifecycleRequest(source="test.pdf", source_type="pdd")
        assert req.deploy_target == "Default"
        assert req.auto_monitor is True
        assert req.require_approval_for_fixes is True

    def test_custom_values(self):
        req = LifecycleRequest(
            source="test.json",
            source_type="ir",
            deploy_target="Production",
            auto_monitor=False,
            require_approval_for_fixes=False,
        )
        assert req.source_type == "ir"
        assert req.deploy_target == "Production"

    def test_serialization_roundtrip(self):
        req = LifecycleRequest(source="desc", source_type="natural_language")
        data = req.model_dump()
        req2 = LifecycleRequest.model_validate(data)
        assert req2.source == req.source


class TestDeploymentRecord:
    def test_defaults(self):
        rec = DeploymentRecord(
            process_key="proc1",
            release_key="rel1",
            package_id="pkg1",
            folder="Default",
        )
        assert rec.version == "1.0.0"
        assert isinstance(rec.deployed_at, datetime)

    def test_ir_snapshot(self):
        rec = DeploymentRecord(
            process_key="p",
            release_key="r",
            package_id="pkg",
            folder="F",
            ir_snapshot={"process_name": "test"},
        )
        assert rec.ir_snapshot["process_name"] == "test"


class TestExecutionLog:
    def test_minimal(self):
        log = ExecutionLog(
            job_id="j1",
            state="Faulted",
            started_at=datetime(2026, 1, 1),
        )
        assert log.ended_at is None
        assert log.robot_logs == []


class TestMonitoringReport:
    def test_defaults(self):
        report = MonitoringReport(
            process_key="proc1",
            period_start=datetime(2026, 1, 1),
            period_end=datetime(2026, 1, 2),
        )
        assert report.total_jobs == 0
        assert report.success_rate == 1.0

    def test_with_failures(self):
        report = MonitoringReport(
            process_key="proc1",
            period_start=datetime(2026, 1, 1),
            period_end=datetime(2026, 1, 2),
            total_jobs=10,
            successful=8,
            faulted=2,
            success_rate=0.8,
            errors_by_type={"SelectorNotFoundException": 2},
        )
        assert report.faulted == 2
        assert "SelectorNotFoundException" in report.errors_by_type


class TestDiagnosisResult:
    def test_valid_confidence(self):
        diag = DiagnosisResult(
            root_cause="test",
            category="code_bug",
            confidence=0.85,
            recommended_action="fix_code",
        )
        assert diag.confidence == 0.85

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            DiagnosisResult(
                root_cause="test",
                category="code_bug",
                confidence=1.5,
                recommended_action="fix_code",
            )

    def test_all_categories(self):
        for cat in [
            "selector_drift", "data_schema_change", "system_timeout",
            "credential_expiry", "business_rule_violation", "code_bug",
            "infrastructure", "unknown",
        ]:
            diag = DiagnosisResult(
                root_cause="test",
                category=cat,
                confidence=0.5,
                recommended_action="no_action",
            )
            assert diag.category == cat


class TestFixProposal:
    def test_auto_id(self):
        fp = FixProposal(
            description="Fix selectors",
            risk_level="medium",
        )
        assert len(fp.proposal_id) == 12
        assert fp.requires_redeployment is True

    def test_with_changes(self):
        fp = FixProposal(
            description="Fix code",
            risk_level="high",
            changes=[
                ProposedChange(
                    file_path="Process.xaml",
                    change_type="modify",
                    description="Fix null reference",
                    before="old",
                    after="new",
                ),
            ],
        )
        assert len(fp.changes) == 1
        assert fp.changes[0].change_type == "modify"


class TestDriftReport:
    def test_creation(self):
        dr = DriftReport(
            process_key="proc1",
            drift_type="success_rate_decline",
            severity="high",
            baseline_value=0.95,
            current_value=0.60,
            recommendation="Investigate failures",
        )
        assert dr.severity == "high"
        assert isinstance(dr.detected_at, datetime)


class TestLifecycleState:
    def test_minimal(self):
        req = LifecycleRequest(source="test.pdf", source_type="pdd")
        state = LifecycleState(request=req)
        assert state.phase == LifecyclePhase.AUTHORING
        assert state.iteration == 0
        assert state.max_iterations == 3
        assert state.errors == []
        assert state.history == []

    def test_serialization(self):
        req = LifecycleRequest(source="test.pdf", source_type="pdd")
        state = LifecycleState(request=req, project_dir="/tmp/test")
        data = state.model_dump()
        state2 = LifecycleState.model_validate(data)
        assert state2.project_dir == "/tmp/test"


class TestLifecycleEvent:
    def test_creation(self):
        event = LifecycleEvent(
            phase=LifecyclePhase.AUTHORING,
            event_type="test",
            detail="test detail",
        )
        assert isinstance(event.timestamp, datetime)
        assert event.metadata == {}
