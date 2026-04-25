"""Tests for QALoopRunner — traceback classification + subprocess execution."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from rpa_architect.lifecycle.qa_loop import (
    QALoopRunner,
    QARunResult,
    classify_traceback,
)


# ── classify_traceback ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "stderr,expected_type",
    [
        (
            "Traceback (most recent call last):\n"
            "playwright._impl._errors.TimeoutError: Timeout 1500ms exceeded.",
            "TimeoutException",
        ),
        ("waiting for selector \"#missing\" failed", "SelectorNotFoundException"),
        ("locator.click: Target page.locator('#x') not found", "SelectorNotFoundException"),
        ("strict mode violation: locator resolved to 3 elements", "SelectorNotFoundException"),
        ("AttributeError: 'NoneType' object has no attribute 'click'", "NullReferenceException"),
        ("ValueError: nope", "ValueError"),
    ],
)
def test_classify_traceback_recognised_patterns(stderr: str, expected_type: str) -> None:
    exc_type, _ = classify_traceback(stderr)
    assert exc_type == expected_type


def test_classify_traceback_extracts_message() -> None:
    stderr = (
        "Traceback (most recent call last):\n"
        "  File 'x.py', line 1\n"
        "TimeoutError: Timeout 30000ms exceeded.\n"
    )
    exc_type, msg = classify_traceback(stderr)
    assert exc_type == "TimeoutException"
    assert msg == "Timeout 30000ms exceeded."


def test_classify_traceback_empty_input() -> None:
    assert classify_traceback("") == ("", "")


# ── QALoopRunner subprocess execution ──────────────────────────────────


def _write_main(project_dir: Path, body: str) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "main.py").write_text(body)
    (project_dir / "processes").mkdir(exist_ok=True)


@pytest.mark.asyncio
async def test_run_passes_when_main_exits_zero(tmp_path: Path) -> None:
    _write_main(tmp_path, "print('ok')\n")
    result = await QALoopRunner(timeout_seconds=10).run(tmp_path)
    assert isinstance(result, QARunResult)
    assert result.passed is True
    assert result.failure is None
    assert result.iterations == 1


@pytest.mark.asyncio
async def test_run_captures_failure_bundle_on_exit_nonzero(tmp_path: Path) -> None:
    _write_main(
        tmp_path,
        "raise RuntimeError('boom')\n",
    )
    result = await QALoopRunner(timeout_seconds=10).run(tmp_path, iteration=2)
    assert result.passed is False
    assert result.failure is not None
    assert result.iterations == 2
    assert result.failure.exception_type == "RuntimeError"
    assert "boom" in result.failure.exception_message
    assert result.failure.project_dir == str(tmp_path.resolve())


@pytest.mark.asyncio
async def test_run_classifies_playwright_timeout(tmp_path: Path) -> None:
    """Generated tracebacks containing TimeoutError get the canonical mapped name."""
    _write_main(
        tmp_path,
        "raise TimeoutError('Timeout 1500ms exceeded.')\n",
    )
    result = await QALoopRunner(timeout_seconds=10).run(tmp_path)
    assert result.passed is False
    assert result.failure is not None
    assert result.failure.exception_type == "TimeoutException"


@pytest.mark.asyncio
async def test_run_returns_missing_artifact_when_no_main(tmp_path: Path) -> None:
    result = await QALoopRunner(timeout_seconds=10).run(tmp_path)
    assert result.passed is False
    assert result.failure is not None
    assert result.failure.exception_type == "MissingArtifact"


@pytest.mark.asyncio
async def test_run_kills_subprocess_on_timeout(tmp_path: Path) -> None:
    _write_main(
        tmp_path,
        "import time\ntime.sleep(60)\n",
    )
    result = await QALoopRunner(timeout_seconds=0.5).run(tmp_path)
    assert result.passed is False
    assert result.failure is not None
    assert result.failure.exception_type == "TimeoutException"
    assert "0.5s" in result.failure.exception_message


@pytest.mark.asyncio
async def test_run_default_env_forces_headless(tmp_path: Path) -> None:
    """Lifecycle-driven QA defaults to headless. Caller can override per-run."""
    _write_main(
        tmp_path,
        "import os, sys\nsys.exit(0 if os.environ.get('RPA_HEADLESS') == '1' else 1)\n",
    )
    result = await QALoopRunner(timeout_seconds=10).run(tmp_path)
    assert result.passed is True
