"""Tests for lifecycle agent graph construction and routing."""

from datetime import datetime, timedelta

from rpa_architect.lifecycle.state import (
    AuthoringOutputs,
    DiagnosisResult,
    FixOutputs,
    LifecycleRequest,
    LifecycleState,
    MonitoringOutputs,
    MonitoringReport,
)
from rpa_architect.lifecycle.agent import (
    _route_after_validate,
    _route_after_monitor,
    _route_after_diagnose,
    _route_after_approval,
    _route_after_apply,
    create_lifecycle_graph,
)


def _make_state(**overrides) -> LifecycleState:
    req = LifecycleRequest(source="test.pdf", source_type="pdd")
    defaults = dict(request=req, max_iterations=3)
    # Convenience: lift legacy flat kwargs into their nested sub-records
    # so existing routing tests stay terse.
    if "approval_status" in overrides:
        overrides["fix"] = FixOutputs(approval_status=overrides.pop("approval_status"))
    monitoring_kwargs: dict = {}
    for legacy in ("monitoring_report", "diagnosis", "drift_report"):
        if legacy in overrides:
            key = "report" if legacy == "monitoring_report" else legacy
            monitoring_kwargs[key] = overrides.pop(legacy)
    if monitoring_kwargs:
        overrides["monitoring"] = MonitoringOutputs(**monitoring_kwargs)
    authoring_kwargs: dict = {}
    for legacy in ("ir", "generation_result", "project_dir"):
        if legacy in overrides:
            authoring_kwargs[legacy] = overrides.pop(legacy)
    if authoring_kwargs:
        overrides["authoring"] = AuthoringOutputs(**authoring_kwargs)
    defaults.update(overrides)
    return LifecycleState(**defaults)


class TestRouteAfterValidate:
    def test_clean_routes_to_deploy(self):
        state = _make_state(errors=[])
        assert _route_after_validate(state) == "deploy"

    def test_errors_with_budget_routes_to_author(self):
        state = _make_state(errors=["compilation failed"], iteration=1)
        assert _route_after_validate(state) == "author"

    def test_errors_exhausted_routes_to_deploy(self):
        state = _make_state(errors=["still failing"], iteration=3)
        assert _route_after_validate(state) == "deploy"


class TestRouteAfterMonitor:
    def test_healthy_routes_to_end(self):
        report = MonitoringReport(
            process_key="test",
            period_start=datetime.utcnow() - timedelta(hours=1),
            period_end=datetime.utcnow(),
            total_jobs=10,
            successful=10,
            faulted=0,
            success_rate=1.0,
        )
        state = _make_state(monitoring_report=report)
        assert _route_after_monitor(state) == "__end__"

    def test_faulted_routes_to_diagnose(self):
        report = MonitoringReport(
            process_key="test",
            period_start=datetime.utcnow() - timedelta(hours=1),
            period_end=datetime.utcnow(),
            total_jobs=10,
            successful=7,
            faulted=3,
            success_rate=0.7,
        )
        state = _make_state(monitoring_report=report)
        assert _route_after_monitor(state) == "diagnose"

    def test_no_report_routes_to_end(self):
        state = _make_state(monitoring_report=None)
        assert _route_after_monitor(state) == "__end__"


class TestRouteAfterDiagnose:
    def test_fix_code_routes_to_propose(self):
        diag = DiagnosisResult(
            root_cause="bug",
            category="code_bug",
            confidence=0.9,
            recommended_action="fix_code",
        )
        state = _make_state(diagnosis=diag)
        assert _route_after_diagnose(state) == "fix"

    def test_update_selectors_routes_to_propose(self):
        diag = DiagnosisResult(
            root_cause="drift",
            category="selector_drift",
            confidence=0.8,
            recommended_action="update_selectors",
        )
        state = _make_state(diagnosis=diag)
        assert _route_after_diagnose(state) == "fix"

    def test_escalate_routes_to_end(self):
        diag = DiagnosisResult(
            root_cause="unknown",
            category="unknown",
            confidence=0.3,
            recommended_action="escalate_to_human",
        )
        state = _make_state(diagnosis=diag)
        assert _route_after_diagnose(state) == "__end__"

    def test_no_action_routes_to_end(self):
        diag = DiagnosisResult(
            root_cause="transient",
            category="system_timeout",
            confidence=0.5,
            recommended_action="no_action",
        )
        state = _make_state(diagnosis=diag)
        assert _route_after_diagnose(state) == "__end__"


class TestRouteAfterApproval:
    def test_approved_routes_to_apply(self):
        state = _make_state(approval_status="approved")
        assert _route_after_approval(state) == "apply_fix"

    def test_rejected_routes_to_end(self):
        state = _make_state(approval_status="rejected")
        assert _route_after_approval(state) == "__end__"

    def test_pending_routes_to_end(self):
        state = _make_state(approval_status="pending")
        assert _route_after_approval(state) == "__end__"


class TestRouteAfterApply:
    def test_within_budget_routes_to_validate(self):
        state = _make_state(iteration=1)
        assert _route_after_apply(state) == "validate_gate"

    def test_exhausted_routes_to_end(self):
        state = _make_state(iteration=3)
        assert _route_after_apply(state) == "__end__"


class TestCreateLifecycleGraph:
    def test_graph_compiles(self):
        graph = create_lifecycle_graph()
        assert graph is not None

    def test_graph_has_nodes(self):
        graph = create_lifecycle_graph()
        # Verify the graph has the expected node structure
        node_names = set(graph.get_graph().nodes.keys())
        expected = {
            "author",
            "validate_gate",
            "deploy",
            "monitor",
            "diagnose",
            "fix",
            "approval_gate",
            "apply_fix",
        }
        assert expected.issubset(node_names)
