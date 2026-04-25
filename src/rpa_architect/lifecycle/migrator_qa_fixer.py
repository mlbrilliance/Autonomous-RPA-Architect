"""MigratorQAFixer — patch a migrator-emitted Python+Playwright project.

Sister to :class:`SwarmFaultFixer`. SwarmFaultFixer claims XAML-backed
failures (``failure.xaml_files`` non-empty); this fixer claims the other
side: failures from the migrator output, where the artifact is a directory
of Python files under ``processes/`` plus a top-level ``main.py``.

Two narrow remediations covered today; everything else escalates so a
human can look. Keeps the fixer cheap, predictable, and easy to extend
as patterns emerge.

* **Timeout** — bumps every ``timeout=N`` kwarg in ``processes/*.py`` by 5 s,
  capped at 30 s. Mirrors the YouTube QA loop's "let it wait longer" fix.
* **Selector miss** — flags the offending ``processes/*.py`` for human
  review with ``requires_escalation=True``. Re-harvesting against the live
  target is the right answer here, but it needs a target URL we don't
  always have at fix-time; defer to the human until the lifecycle agent
  threads the IR through.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rpa_architect.lifecycle.fault_fixer import FixOutcome
from rpa_architect.lifecycle.state import FailureBundle

logger = logging.getLogger(__name__)

# Match ``timeout=N`` only as a kwarg in a call (followed by ``,`` or ``)``),
# and only inside a line that already looks like ``await page.…(…)`` — keeps
# us out of comments, docstrings, and string literals where the substring may
# legitimately appear without being a real kwarg.
_TIMEOUT_KWARG_RE = re.compile(r"\btimeout\s*=\s*(\d+)\s*(?=[,)])")
_AWAIT_PAGE_LINE_RE = re.compile(r"^\s*[\w.]*await\s+.*\bpage\b.*$")
_TIMEOUT_BUMP_MS = 5_000
_TIMEOUT_CAP_MS = 30_000


def _atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically — temp file + os.replace.

    Defensive: a fix loop that crashes mid-write would otherwise leave
    ``processes/foo.py`` corrupt and break every later iteration.
    """
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp_name, str(path))
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


@dataclass
class MigratorQAFixer:
    """FaultFixer for python+playwright artifacts emitted by the migrator."""

    name: str = "migrator_qa"

    async def can_handle(self, failure: FailureBundle) -> bool:
        # Mutex with SwarmFaultFixer: it claims XAML, we claim the python output.
        if failure.xaml_files:
            return False
        if not failure.project_dir:
            return False
        project = Path(failure.project_dir)
        return (project / "main.py").exists() and (project / "processes").is_dir()

    async def fix(self, failure: FailureBundle) -> FixOutcome:
        project = Path(failure.project_dir)
        exc = (failure.exception_type or "").lower()

        if "timeout" in exc:
            return self._bump_timeouts(project)
        if "selector" in exc:
            return self._flag_for_reharvest(project, failure)

        return FixOutcome(
            fixer=self.name,
            success=False,
            requires_escalation=True,
            diagnosis_category="unknown",
            evidence={
                "reason": f"no migrator-side strategy for exception_type={failure.exception_type!r}",
                "project_dir": str(project),
            },
        )

    # ── strategies ────────────────────────────────────────────────────────

    def _bump_timeouts(self, project: Path) -> FixOutcome:
        """Additive +5 s on every ``timeout=N`` in ``processes/*.py``, capped at 30 s.

        Only rewrites lines that look like ``await page.…(…)`` calls so a
        stray ``timeout=…`` in a comment or string literal isn't touched.
        """
        touched: list[str] = []
        bumps: list[tuple[int, int]] = []  # (old_ms, new_ms)
        for py in sorted((project / "processes").glob("*.py")):
            original = py.read_text()
            new_lines: list[str] = []
            file_changed = False
            for line in original.splitlines(keepends=True):
                if not _AWAIT_PAGE_LINE_RE.match(line):
                    new_lines.append(line)
                    continue

                def _bump(match: "re.Match[str]") -> str:
                    old = int(match.group(1))
                    if old >= _TIMEOUT_CAP_MS:
                        return match.group(0)
                    new = min(old + _TIMEOUT_BUMP_MS, _TIMEOUT_CAP_MS)
                    bumps.append((old, new))
                    return f"timeout={new}"

                rewritten = _TIMEOUT_KWARG_RE.sub(_bump, line)
                if rewritten != line:
                    file_changed = True
                new_lines.append(rewritten)

            if file_changed:
                _atomic_write_text(py, "".join(new_lines))
                touched.append(py.name)

        if not touched:
            logger.info("No timeout kwargs to bump in %s; escalating.", project)
            return FixOutcome(
                fixer=self.name,
                success=False,
                requires_escalation=True,
                diagnosis_category="system_timeout",
                evidence={"reason": "no timeout= kwargs found", "project_dir": str(project)},
            )

        evidence: dict[str, Any] = {
            "files_patched": touched,
            "bumps": bumps,
            "project_dir": str(project),
        }
        logger.info("Bumped timeouts in %s: %s", project, bumps)
        return FixOutcome(
            fixer=self.name,
            success=True,
            requires_escalation=False,
            diagnosis_category="system_timeout",
            evidence=evidence,
        )

    def _flag_for_reharvest(self, project: Path, failure: FailureBundle) -> FixOutcome:
        """Selector drift needs live re-harvesting; escalate with structured pointers."""
        return FixOutcome(
            fixer=self.name,
            success=False,
            requires_escalation=True,
            diagnosis_category="selector_drift",
            evidence={
                "reason": "selector drift in migrated artifact — re-harvest needed",
                "project_dir": str(project),
                "process_files": sorted(p.name for p in (project / "processes").glob("*.py")),
                "exception_message": failure.exception_message,
            },
        )
