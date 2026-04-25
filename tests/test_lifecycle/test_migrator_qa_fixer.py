"""Tests for MigratorQAFixer — patches python+playwright artifacts."""

from __future__ import annotations

from pathlib import Path

import pytest

from rpa_architect.lifecycle.migrator_qa_fixer import MigratorQAFixer
from rpa_architect.lifecycle.state import FailureBundle


def _project(tmp_path: Path, *, with_processes: bool = True) -> Path:
    (tmp_path / "main.py").write_text("# stub")
    if with_processes:
        (tmp_path / "processes").mkdir()
    return tmp_path


def _bundle(project_dir: Path | str = "", **kwargs: object) -> FailureBundle:
    defaults = dict(
        job_id="qa-iter-1",
        process_key="proj",
        state="Faulted",
        exception_type="TimeoutException",
        exception_message="Timeout 1500ms exceeded.",
        project_dir=str(project_dir),
    )
    defaults.update(kwargs)  # type: ignore[arg-type]
    return FailureBundle(**defaults)  # type: ignore[arg-type]


# ── can_handle ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_declines_xaml_failures(tmp_path: Path) -> None:
    """SwarmFaultFixer owns XAML; we must stay out of its lane."""
    project = _project(tmp_path)
    bundle = _bundle(project, xaml_files={"Main.xaml": "<x/>"})
    assert await MigratorQAFixer().can_handle(bundle) is False


@pytest.mark.asyncio
async def test_declines_when_project_dir_empty() -> None:
    assert await MigratorQAFixer().can_handle(_bundle("")) is False


@pytest.mark.asyncio
async def test_declines_when_main_py_missing(tmp_path: Path) -> None:
    (tmp_path / "processes").mkdir()
    assert await MigratorQAFixer().can_handle(_bundle(tmp_path)) is False


@pytest.mark.asyncio
async def test_claims_python_playwright_project(tmp_path: Path) -> None:
    project = _project(tmp_path)
    assert await MigratorQAFixer().can_handle(_bundle(project)) is True


# ── timeout bumping ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bumps_timeouts_in_process_files(tmp_path: Path) -> None:
    project = _project(tmp_path)
    (project / "processes" / "process_x.py").write_text(
        "await page.locator('#a').wait_for(timeout=1500)\n"
        "await page.locator('#b').wait_for(timeout=20000)\n"
    )
    outcome = await MigratorQAFixer().fix(_bundle(project))
    assert outcome.success is True
    assert outcome.requires_escalation is False
    text = (project / "processes" / "process_x.py").read_text()
    assert "timeout=6500" in text
    assert "timeout=25000" in text
    assert sorted(outcome.evidence["bumps"]) == [(1500, 6500), (20000, 25000)]


@pytest.mark.asyncio
async def test_caps_bumps_at_30s(tmp_path: Path) -> None:
    project = _project(tmp_path)
    (project / "processes" / "process_x.py").write_text(
        "await page.locator('#a').wait_for(timeout=27000)\n"
    )
    await MigratorQAFixer().fix(_bundle(project))
    text = (project / "processes" / "process_x.py").read_text()
    # 27000 + 5000 = 32000, cap at 30000.
    assert "timeout=30000" in text


@pytest.mark.asyncio
async def test_skips_already_at_cap(tmp_path: Path) -> None:
    """Anything ≥30 s is left alone — bumping would loop indefinitely."""
    project = _project(tmp_path)
    (project / "processes" / "process_x.py").write_text(
        "await page.locator('#a').wait_for(timeout=30000)\n"
    )
    outcome = await MigratorQAFixer().fix(_bundle(project))
    # No bumps applied → escalates so the human/lifecycle stops looping.
    assert outcome.success is False
    assert outcome.requires_escalation is True


@pytest.mark.asyncio
async def test_escalates_when_no_timeout_kwargs_present(tmp_path: Path) -> None:
    project = _project(tmp_path)
    (project / "processes" / "process_x.py").write_text(
        "await page.locator('#a').click()\n"
    )
    outcome = await MigratorQAFixer().fix(_bundle(project))
    assert outcome.success is False
    assert outcome.requires_escalation is True


# ── selector drift escalation ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_selector_drift_always_escalates(tmp_path: Path) -> None:
    project = _project(tmp_path)
    (project / "processes" / "process_x.py").write_text("# anything")
    outcome = await MigratorQAFixer().fix(
        _bundle(project, exception_type="SelectorNotFoundException")
    )
    assert outcome.success is False
    assert outcome.requires_escalation is True
    assert outcome.diagnosis_category == "selector_drift"
    assert "process_x.py" in outcome.evidence["process_files"]


# ── regex safety: comments + string literals are not touched ───────────


@pytest.mark.asyncio
async def test_does_not_rewrite_timeout_in_comments_or_strings(tmp_path: Path) -> None:
    """The regex must match real kwargs, not substrings inside comments / strings.

    Otherwise a ``# timeout=1000`` note or an f-string log message gets
    silently corrupted on every fix iteration.
    """
    project = _project(tmp_path)
    src = (
        '"""See: https://example.com/api?timeout=1500 — keep as-is."""\n'
        "# Increase timeout=1500 if upstream is slow\n"
        "logger.info('using timeout=1500 for X')\n"
        "await page.locator('#real').wait_for(timeout=1500)\n"
    )
    (project / "processes" / "process_x.py").write_text(src)
    await MigratorQAFixer().fix(_bundle(project))
    text = (project / "processes" / "process_x.py").read_text()
    assert "timeout=6500" in text  # real kwarg got bumped
    # The other three appearances of "timeout=1500" remain untouched.
    assert text.count("timeout=1500") == 3


@pytest.mark.asyncio
async def test_atomic_write_leaves_no_temp_files(tmp_path: Path) -> None:
    """After a successful fix, only the original .py files remain."""
    project = _project(tmp_path)
    (project / "processes" / "process_x.py").write_text(
        "await page.locator('#a').wait_for(timeout=1500)\n"
    )
    await MigratorQAFixer().fix(_bundle(project))
    files = sorted(p.name for p in (project / "processes").iterdir())
    assert files == ["process_x.py"]


# ── unknown exception escalates ────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_exception_escalates(tmp_path: Path) -> None:
    project = _project(tmp_path)
    outcome = await MigratorQAFixer().fix(
        _bundle(project, exception_type="ValueError")
    )
    assert outcome.success is False
    assert outcome.requires_escalation is True
    assert outcome.diagnosis_category == "unknown"
