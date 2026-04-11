"""Tests for observability tracer and dashboard."""

import pytest
import asyncio

from rpa_architect.observability.tracer import (
    AgentSpan,
    AgentTrace,
    LifecycleTracer,
)


class TestAgentSpan:
    def test_creation(self):
        span = AgentSpan(name="test_node")
        assert span.name == "test_node"
        assert span.status == "ok"
        assert span.parent_id is None
        assert len(span.span_id) == 16

    def test_with_attributes(self):
        span = AgentSpan(name="deploy", attributes={"target": "prod"})
        assert span.attributes["target"] == "prod"


class TestAgentTrace:
    def test_creation(self):
        trace = AgentTrace(process_name="test_proc")
        assert len(trace.trace_id) == 32
        assert trace.spans == []
        assert not trace.has_errors

    def test_has_errors(self):
        trace = AgentTrace()
        trace.spans.append(AgentSpan(name="ok_span"))
        assert not trace.has_errors
        trace.spans.append(AgentSpan(name="bad_span", status="error"))
        assert trace.has_errors

    def test_duration(self):
        from datetime import datetime, timedelta
        trace = AgentTrace()
        trace.started_at = datetime(2026, 1, 1, 0, 0, 0)
        trace.completed_at = datetime(2026, 1, 1, 0, 0, 1)
        assert trace.duration_ms == 1000.0


class TestLifecycleTracer:
    @pytest.mark.asyncio
    async def test_basic_span(self):
        tracer = LifecycleTracer(process_name="test")
        async with tracer.span("author") as s:
            s.attributes["files"] = 5
        trace = tracer.complete()
        assert len(trace.spans) == 1
        assert trace.spans[0].name == "author"
        assert trace.spans[0].duration_ms > 0

    @pytest.mark.asyncio
    async def test_nested_spans(self):
        tracer = LifecycleTracer()
        async with tracer.span("parent"):
            async with tracer.span("child") as child:
                pass
        trace = tracer.complete()
        assert len(trace.spans) == 2
        child_span = trace.spans[0]  # child completes first
        parent_span = trace.spans[1]
        assert child_span.parent_id == parent_span.span_id

    @pytest.mark.asyncio
    async def test_error_span(self):
        tracer = LifecycleTracer()
        with pytest.raises(ValueError):
            async with tracer.span("failing"):
                raise ValueError("test error")
        trace = tracer.complete()
        assert trace.spans[0].status == "error"
        assert trace.spans[0].error == "test error"
        assert trace.has_errors

    @pytest.mark.asyncio
    async def test_export_json(self, tmp_path):
        tracer = LifecycleTracer(process_name="export_test")
        async with tracer.span("node1"):
            pass
        trace = tracer.complete()
        json_path = tmp_path / "trace.json"
        result = tracer.export_json(json_path)
        assert json_path.exists()
        assert "export_test" in result
        assert "node1" in result


class TestTestRunner:
    """Tests for the test runner module."""

    def test_structural_validation_with_tests(self, tmp_path):
        from rpa_architect.testing.test_runner import _run_structural_validation

        (tmp_path / "TestProcess.xaml").write_text("<Activity>test case content</Activity>")
        result = _run_structural_validation(tmp_path)
        assert result.passed == 1
        assert result.failed == 0
        assert result.success

    def test_structural_validation_no_tests(self, tmp_path):
        from rpa_architect.testing.test_runner import _run_structural_validation

        result = _run_structural_validation(tmp_path)
        assert result.total == 0

    def test_structural_validation_empty_test(self, tmp_path):
        from rpa_architect.testing.test_runner import _run_structural_validation

        (tmp_path / "TestEmpty.xaml").write_text("")
        result = _run_structural_validation(tmp_path)
        assert result.failed == 1

    def test_result_success_property(self):
        from rpa_architect.testing.test_runner import TestRunResult

        assert TestRunResult(passed=5, total=5).success
        assert not TestRunResult(passed=3, failed=2, total=5).success
        assert not TestRunResult(total=0).success
