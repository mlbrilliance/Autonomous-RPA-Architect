"""Integration tests for the qa_run lifecycle node.

The node is a thin wrapper that delegates to ``MigratorQALoop``. These
tests confirm the wiring (state → loop → state.errors) is correct without
spinning up a real browser — we use a fake project that exits cleanly so
``QALoopRunner`` reports passed without ever launching Playwright.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from rpa_architect.lifecycle.nodes import qa_run_node
from rpa_architect.lifecycle.state import (
    AuthoringOutputs,
    LifecycleRequest,
    LifecycleState,
)


def _state_with_migrator_output(project_dir: Path) -> LifecycleState:
    return LifecycleState(
        request=LifecycleRequest(source="x", source_type="pdd"),
        authoring=AuthoringOutputs(migrator_output_dir=str(project_dir)),
    )


def _write_fake_project(root: Path, *, exit_code: int) -> None:
    """Write a minimal project that ``QALoopRunner.run`` will accept."""
    (root / "processes").mkdir(parents=True, exist_ok=True)
    (root / "main.py").write_text(
        f"import sys, os\n"
        f"# subprocess inherits RPA_HEADLESS=1 — proves env wiring\n"
        f"assert os.environ.get('RPA_HEADLESS') == '1'\n"
        f"sys.exit({exit_code})\n"
    )


@pytest.mark.asyncio
async def test_qa_run_passes_when_subprocess_exits_zero(tmp_path: Path) -> None:
    _write_fake_project(tmp_path, exit_code=0)
    state = _state_with_migrator_output(tmp_path)
    result = await qa_run_node(state)
    assert result.errors == []
    event_types = [e.event_type for e in result.history]
    assert "qa_run_started" in event_types
    assert "qa_run_passed" in event_types


@pytest.mark.asyncio
async def test_qa_run_records_failure_when_subprocess_exits_nonzero(tmp_path: Path) -> None:
    _write_fake_project(tmp_path, exit_code=1)
    state = _state_with_migrator_output(tmp_path)
    result = await qa_run_node(state)
    assert result.errors  # populated
    assert "FAILED" in result.errors[0]
    assert any(e.event_type == "qa_run_failed" for e in result.history)


def test_qa_run_node_is_async() -> None:
    """The node must be awaitable for LangGraph to call it."""
    assert asyncio.iscoroutinefunction(qa_run_node)
