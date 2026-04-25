"""Tests for MigratorQALoop — bounded build/test/fix/retest loop."""

from __future__ import annotations

from pathlib import Path

import pytest

from rpa_architect.lifecycle.fault_fixer import FixerRegistry, FixOutcome
from rpa_architect.lifecycle.migrator_qa_orchestrator import (
    MigratorQALoop,
    MigratorQAReport,
)
from rpa_architect.lifecycle.qa_loop import QARunResult
from rpa_architect.lifecycle.state import FailureBundle


class _ScriptedRunner:
    """Yields a scripted sequence of QARunResults; records call count."""

    def __init__(self, results: list[QARunResult]) -> None:
        self._results = results
        self.calls = 0

    async def run(self, project_dir: Path, *, iteration: int = 1) -> QARunResult:  # noqa: ARG002
        idx = min(self.calls, len(self._results) - 1)
        self.calls += 1
        return self._results[idx]


def _passing(iteration: int = 1) -> QARunResult:
    return QARunResult(passed=True, iterations=iteration)


def _failing(iteration: int = 1, exception_type: str = "TimeoutException") -> QARunResult:
    bundle = FailureBundle(
        job_id=f"qa-iter-{iteration}",
        process_key="proj",
        state="Faulted",
        exception_type=exception_type,
        exception_message="Timeout 1500ms",
        project_dir="/tmp/proj",
    )
    return QARunResult(passed=False, failure=bundle, iterations=iteration)


def _ok_outcome() -> FixOutcome:
    return FixOutcome(fixer="migrator_qa", success=True, requires_escalation=False)


def _escalation_outcome() -> FixOutcome:
    return FixOutcome(fixer="migrator_qa", success=False, requires_escalation=True)


class _ScriptedRegistry(FixerRegistry):
    """FixerRegistry stub — yields the next outcome and records the bundle."""

    def __init__(self, outcomes: list[FixOutcome]) -> None:
        super().__init__([])
        self._outcomes = outcomes
        self.bundles: list[FailureBundle] = []

    async def remediate(self, failure: FailureBundle) -> FixOutcome:
        self.bundles.append(failure)
        idx = min(len(self.bundles) - 1, len(self._outcomes) - 1)
        return self._outcomes[idx]


@pytest.mark.asyncio
async def test_passes_first_iteration_no_fix_needed(tmp_path: Path) -> None:
    runner = _ScriptedRunner([_passing()])
    registry = _ScriptedRegistry([])
    loop = MigratorQALoop(runner=runner, registry=registry)
    report = await loop.run(tmp_path)
    assert isinstance(report, MigratorQAReport)
    assert report.passed is True
    assert report.iterations == 1
    assert report.fix_outcomes == []
    assert runner.calls == 1


@pytest.mark.asyncio
async def test_fixes_then_passes_on_retry(tmp_path: Path) -> None:
    runner = _ScriptedRunner([_failing(1), _passing(2)])
    registry = _ScriptedRegistry([_ok_outcome()])
    loop = MigratorQALoop(runner=runner, registry=registry, max_iterations=3)
    report = await loop.run(tmp_path)
    assert report.passed is True
    assert report.iterations == 2
    assert len(report.fix_outcomes) == 1
    assert report.fix_outcomes[0].success is True
    assert runner.calls == 2


@pytest.mark.asyncio
async def test_escalation_halts_loop(tmp_path: Path) -> None:
    runner = _ScriptedRunner([_failing(1)])
    registry = _ScriptedRegistry([_escalation_outcome()])
    loop = MigratorQALoop(runner=runner, registry=registry, max_iterations=3)
    report = await loop.run(tmp_path)
    assert report.passed is False
    # Loop stops at iteration 1 (the run that produced the failure).
    assert report.iterations == 1
    assert len(report.fix_outcomes) == 1
    assert runner.calls == 1, "should not retry after escalation"


@pytest.mark.asyncio
async def test_exhausts_budget_without_pass(tmp_path: Path) -> None:
    runner = _ScriptedRunner([_failing(1), _failing(2), _failing(3)])
    registry = _ScriptedRegistry([_ok_outcome(), _ok_outcome()])
    loop = MigratorQALoop(runner=runner, registry=registry, max_iterations=3)
    report = await loop.run(tmp_path)
    assert report.passed is False
    assert report.iterations == 3
    assert len(report.fix_outcomes) == 2
    assert runner.calls == 3


@pytest.mark.asyncio
async def test_summary_string_reports_state(tmp_path: Path) -> None:
    runner = _ScriptedRunner([_passing()])
    loop = MigratorQALoop(runner=runner, registry=_ScriptedRegistry([]))
    report = await loop.run(tmp_path)
    assert "passed" in report.summary()
    assert "1 iteration" in report.summary()
