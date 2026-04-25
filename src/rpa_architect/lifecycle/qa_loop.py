"""QALoopRunner — execute a migrator-emitted Playwright project, capture failures.

Runs ``python main.py`` from a generated project directory in a subprocess,
captures stdout/stderr, and converts a non-zero exit into a
:class:`FailureBundle` the lifecycle FixerRegistry can route to the
:class:`MigratorQAFixer`. Mirrors the YouTube QA-loop pattern (build →
headed test → find bugs → fix → retest), wired into this repo's actual
subject (UiPath migration), not a generic form demo.

Subprocess instead of importlib because the migrated project is standalone
(its ``pyproject.toml`` declares only ``playwright`` — it does not import
``rpa_architect``). Cleanest isolation; no sys.path pollution.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from rpa_architect.lifecycle.state import FailureBundle

logger = logging.getLogger(__name__)


# Traceback substring → exception_type string the FixProposalFixer convention expects.
# Order matters: more specific patterns first.
_EXC_TYPE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"playwright\._impl\._errors\.TimeoutError"), "TimeoutException"),
    (re.compile(r"TimeoutError"), "TimeoutException"),
    (re.compile(r"strict mode violation"), "SelectorNotFoundException"),
    (re.compile(r"locator\.[a-z_]+: Target.*?not found"), "SelectorNotFoundException"),
    (re.compile(r"waiting for selector"), "SelectorNotFoundException"),
    (re.compile(r"AttributeError: 'NoneType'"), "NullReferenceException"),
)


@dataclass
class QARunResult:
    """Outcome of a single QA-loop iteration."""

    passed: bool
    failure: FailureBundle | None = None
    iterations: int = 1
    screenshots: list[Path] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""


def classify_traceback(stderr: str) -> tuple[str, str]:
    """Return ``(exception_type, exception_message)`` parsed from a traceback.

    Empty strings if nothing recognisable is found. Public so tests can
    pin the convention; lifecycle code only consumes the bundle.
    """
    if not stderr:
        return "", ""

    exc_type = ""
    for pattern, mapped in _EXC_TYPE_PATTERNS:
        if pattern.search(stderr):
            exc_type = mapped
            break

    # Last "ExceptionClass: message" line in the traceback is conventionally the cause.
    last_msg = ""
    for line in reversed(stderr.splitlines()):
        m = re.match(r"^([A-Za-z_][\w.]*Error|[A-Za-z_][\w.]*Exception)\s*:\s*(.*)$", line)
        if m:
            last_msg = m.group(2).strip()
            if not exc_type:
                exc_type = m.group(1).split(".")[-1]
            break

    return exc_type, last_msg


class QALoopRunner:
    """Run a migrator-emitted project and capture any Playwright failure."""

    def __init__(
        self,
        *,
        python_executable: str | None = None,
        timeout_seconds: float = 120.0,
        env: dict[str, str] | None = None,
    ) -> None:
        self._python = python_executable or sys.executable
        self._timeout = timeout_seconds
        # Default to headless when invoked from the lifecycle agent — this is
        # the CI-like path. Demos that want headed runs override via env.
        base_env = {**os.environ}
        base_env.setdefault("RPA_HEADLESS", "1")
        if env:
            base_env.update(env)
        self._env = base_env

    async def run(self, project_dir: Path, *, iteration: int = 1) -> QARunResult:
        """Execute ``project_dir/main.py`` once and return the outcome.

        Bounded by ``timeout_seconds``. The lifecycle agent calls this in a
        loop; ``iteration`` is forwarded to the result for telemetry only.
        """
        project_dir = Path(project_dir).resolve()
        main_py = project_dir / "main.py"
        if not main_py.exists():
            return QARunResult(
                passed=False,
                iterations=iteration,
                stderr=f"main.py not found in {project_dir}",
                failure=FailureBundle(
                    job_id=f"qa-iter-{iteration}",
                    process_key=project_dir.name,
                    state="Faulted",
                    exception_type="MissingArtifact",
                    exception_message=f"main.py not found in {project_dir}",
                    project_dir=str(project_dir),
                ),
            )

        proc = await asyncio.create_subprocess_exec(
            self._python,
            str(main_py),
            cwd=str(project_dir),
            env=self._env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return QARunResult(
                passed=False,
                iterations=iteration,
                stderr=f"timeout after {self._timeout}s",
                failure=FailureBundle(
                    job_id=f"qa-iter-{iteration}",
                    process_key=project_dir.name,
                    state="Faulted",
                    exception_type="TimeoutException",
                    exception_message=f"QA run exceeded {self._timeout}s",
                    project_dir=str(project_dir),
                ),
            )

        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")

        if proc.returncode == 0:
            logger.info("QA iter %d passed for %s", iteration, project_dir.name)
            return QARunResult(passed=True, iterations=iteration, stdout=stdout, stderr=stderr)

        exc_type, exc_msg = classify_traceback(stderr)
        screenshots = sorted(project_dir.glob("**/screenshots/*.png"))
        bundle = FailureBundle(
            job_id=f"qa-iter-{iteration}",
            process_key=project_dir.name,
            state="Faulted",
            exception_type=exc_type or "RuntimeError",
            exception_message=exc_msg or (stderr.splitlines()[-1] if stderr else ""),
            screenshot_paths=[str(p) for p in screenshots],
            project_dir=str(project_dir),
        )
        logger.warning(
            "QA iter %d failed for %s — %s: %s",
            iteration, project_dir.name, bundle.exception_type, bundle.exception_message,
        )
        return QARunResult(
            passed=False,
            failure=bundle,
            iterations=iteration,
            screenshots=screenshots,
            stdout=stdout,
            stderr=stderr,
        )
