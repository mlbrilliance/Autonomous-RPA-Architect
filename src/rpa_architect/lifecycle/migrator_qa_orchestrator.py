"""MigratorQALoop — bounded build → test → fix → retest loop for migrator output.

Drives a migrator-emitted Python+Playwright project through the YouTube-style
QA loop without touching the LangGraph lifecycle: the loop instantiates the
:class:`FixerRegistry` directly and iterates ``QALoopRunner.run`` until either
the artifact passes or the iteration budget is spent.

Same primitives as the LangGraph fix branch (``FixerRegistry``,
:class:`FailureBundle`, :class:`FixOutcome`) — just orchestrated for the
migrator-output domain instead of the deploy/monitor domain. A future
caller can drop this loop in front of ``deploy`` if/when the migrator
output gets wired into the main lifecycle.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from rpa_architect.lifecycle.fault_fixer import FixerRegistry, FixOutcome
from rpa_architect.lifecycle.qa_loop import QALoopRunner, QARunResult

logger = logging.getLogger(__name__)


@dataclass
class MigratorQAReport:
    """Aggregate outcome of a full QA loop run."""

    passed: bool
    iterations: int
    last_run: QARunResult
    fix_outcomes: list[FixOutcome] = field(default_factory=list)

    def summary(self) -> str:
        verdict = "passed" if self.passed else "FAILED"
        return (
            f"QA {verdict} after {self.iterations} iteration(s); "
            f"{len(self.fix_outcomes)} fix attempt(s)"
        )


@dataclass
class MigratorQALoop:
    """Bounded build/test/fix/retest loop for one migrator-emitted project.

    ``runner`` and ``registry`` are injected so callers can swap in mocks for
    tests (``demo_qa_loop.py`` uses real instances).
    """

    runner: QALoopRunner
    registry: FixerRegistry
    max_iterations: int = 3

    async def run(self, project_dir: Path) -> MigratorQAReport:
        project_dir = Path(project_dir).resolve()
        fix_outcomes: list[FixOutcome] = []

        result = await self.runner.run(project_dir, iteration=1)
        if result.passed:
            return MigratorQAReport(passed=True, iterations=1, last_run=result)

        for iteration in range(2, self.max_iterations + 1):
            assert result.failure is not None  # mypy/runtime guard
            outcome = await self.registry.remediate(result.failure)
            fix_outcomes.append(outcome)
            logger.info(
                "QA iter %d → fixer=%s success=%s escalation=%s",
                iteration - 1, outcome.fixer, outcome.success, outcome.requires_escalation,
            )
            if outcome.requires_escalation or not outcome.success:
                return MigratorQAReport(
                    passed=False,
                    iterations=iteration - 1,
                    last_run=result,
                    fix_outcomes=fix_outcomes,
                )

            result = await self.runner.run(project_dir, iteration=iteration)
            if result.passed:
                return MigratorQAReport(
                    passed=True,
                    iterations=iteration,
                    last_run=result,
                    fix_outcomes=fix_outcomes,
                )

        return MigratorQAReport(
            passed=False,
            iterations=self.max_iterations,
            last_run=result,
            fix_outcomes=fix_outcomes,
        )
