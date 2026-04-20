"""Open a GitHub PR carrying a FixCandidate's patches.

Uses the ``gh`` CLI (already present in the repo's tooling) rather than the
GitHub REST API so that auth picks up the user's local gh session. A
pluggable :class:`CommandRunner` lets tests inject a :class:`FakeRunner`
without shelling out.

The PR body is written to a temp file and passed via ``--body-file`` to
avoid shell-escaping headaches with multi-line exception messages.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from rpa_architect.lifecycle.state import FailureBundle, FixCandidate

logger = logging.getLogger("rpa_architect.lifecycle.swarm.pr_opener")


class CommandRunner(Protocol):
    def run(self, cmd: list[str], *, cwd: str) -> tuple[int, str, str]: ...


class SubprocessRunner:
    """Default runner — shells out via ``subprocess.run``."""

    def run(self, cmd: list[str], *, cwd: str) -> tuple[int, str, str]:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
        return proc.returncode, proc.stdout, proc.stderr


@dataclass
class PROpenResult:
    pr_url: str
    branch: str
    commit_sha: str


class PROpener:
    """Commit a FixCandidate's patches and open a PR via ``gh``."""

    def __init__(
        self,
        *,
        repo_root: Path,
        runner: CommandRunner | None = None,
    ) -> None:
        self._repo_root = Path(repo_root)
        self._runner: CommandRunner = runner or SubprocessRunner()

    def open(
        self,
        *,
        bundle: FailureBundle,
        candidate: FixCandidate,
        base_branch: str,
        staging_url: str,
    ) -> PROpenResult:
        if not candidate.patches:
            raise ValueError("PROpener.open called with a FixCandidate carrying no patches")

        branch = self._branch_name(bundle)
        self._run(["git", "checkout", "-b", branch])

        for file_path, patched_content in candidate.patched_xaml.items():
            target = self._repo_root / file_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(patched_content)
            self._run(["git", "add", str(file_path)])

        commit_msg = self._commit_message(bundle, candidate)
        self._run(["git", "commit", "-m", commit_msg])
        _, sha, _ = self._run(["git", "rev-parse", "HEAD"])

        body_path = self._write_body(bundle, candidate, staging_url)
        title = f"auto-heal: {bundle.exception_type} in {bundle.process_key}"
        rc, out, err = self._run(
            [
                "gh",
                "pr",
                "create",
                "--title",
                title,
                "--body-file",
                str(body_path),
                "--base",
                base_branch,
            ]
        )
        pr_url = _extract_url(out) or _extract_url(err) or ""
        return PROpenResult(pr_url=pr_url, branch=branch, commit_sha=sha.strip())

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _run(self, cmd: list[str]) -> tuple[int, str, str]:
        logger.debug("run: %s", " ".join(cmd))
        rc, out, err = self._runner.run(cmd, cwd=str(self._repo_root))
        if rc != 0:
            logger.warning("command failed (%d): %s\nstderr: %s", rc, " ".join(cmd), err)
        return rc, out, err

    @staticmethod
    def _branch_name(bundle: FailureBundle) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        safe_job = bundle.job_id.replace("/", "-").replace(" ", "-")
        return f"auto-heal/{safe_job}-{ts}"

    @staticmethod
    def _commit_message(bundle: FailureBundle, candidate: FixCandidate) -> str:
        return (
            f"auto-heal: patch {bundle.exception_type} in {bundle.process_key}\n\n"
            f"Specialist: {candidate.specialist}\n"
            f"Confidence: {candidate.confidence:.2f}\n"
            f"Job: {bundle.job_id}\n\n"
            f"{candidate.reasoning}"
        )

    def _write_body(
        self, bundle: FailureBundle, candidate: FixCandidate, staging_url: str
    ) -> Path:
        lines = [
            f"## Auto-heal PR — {bundle.exception_type}",
            "",
            f"**Process:** `{bundle.process_key}`",
            f"**Failed job:** `{bundle.job_id}`",
            f"**Specialist:** `{candidate.specialist}`",
            f"**Confidence:** `{candidate.confidence:.2f}`",
            "",
            "### Exception",
            "```",
            bundle.exception_message,
            "```",
            "",
            "### Proposed patches",
        ]
        for p in candidate.patches:
            lines.extend(
                [
                    f"- `{p.file_path}` — attribute `{p.attribute}`",
                    f"  - before: `{p.old_value}`",
                    f"  - after: `{p.new_value}`",
                    f"  - rationale: {p.rationale}",
                ]
            )
        lines.extend(
            [
                "",
                "### Staging validation",
                f"- Run: {staging_url}",
                "",
                "### Reasoning",
                candidate.reasoning,
                "",
                "_Opened by the Self-Healing Swarm. Human approval required before merge._",
            ]
        )
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, dir=str(self._repo_root)
        )
        tmp.write("\n".join(lines))
        tmp.close()
        return Path(tmp.name)


def _extract_url(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("https://") and "/pull/" in line:
            return line
    return ""
