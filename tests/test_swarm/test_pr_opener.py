"""PR opener: produce a branch, write patched files, invoke `gh pr create`."""

from __future__ import annotations

from pathlib import Path

import pytest

from rpa_architect.lifecycle.state import FailureBundle, FixCandidate, XamlPatch
from rpa_architect.lifecycle.swarm.pr_opener import PROpener, PROpenResult


class FakeRunner:
    """Stand-in for subprocess — records every invocation."""

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self.calls: list[list[str]] = []
        self._responses = responses or {}

    def run(self, cmd: list[str], *, cwd: str) -> tuple[int, str, str]:
        self.calls.append(cmd)
        # Return a canned URL for gh pr create
        if cmd[:3] == ["gh", "pr", "create"]:
            return 0, "https://github.com/org/repo/pull/42\n", ""
        return 0, self._responses.get(" ".join(cmd), ""), ""


def _bundle() -> FailureBundle:
    return FailureBundle(
        job_id="job-1",
        process_key="Invoice",
        state="Faulted",
        exception_message="SelectorNotFoundException: boom",
        exception_type="SelectorNotFoundException",
    )


def _candidate(tmp_path: Path) -> FixCandidate:
    return FixCandidate(
        specialist="selector_repair",
        confidence=0.8,
        diagnosis_category="selector_drift",
        patches=[
            XamlPatch(
                file_path="Main.xaml",
                target_xpath="/a:Activity",
                attribute="Selector",
                old_value="<webctrl id='submit'/>",
                new_value="<webctrl id='submit-v2'/>",
                rationale="re-harvested",
            )
        ],
        reasoning="selector drifted",
        patched_xaml={"Main.xaml": "<Activity>patched</Activity>"},
    )


class TestPROpener:
    def test_creates_branch_writes_file_commits_and_opens_pr(self, tmp_path: Path) -> None:
        # Seed repo: a file we can "patch"
        (tmp_path / "Main.xaml").write_text("<Activity>original</Activity>")
        runner = FakeRunner()
        opener = PROpener(repo_root=tmp_path, runner=runner)

        result = opener.open(
            bundle=_bundle(),
            candidate=_candidate(tmp_path),
            base_branch="main",
            staging_url="https://cloud.uipath.com/org/tenant/jobs/staging-42",
        )

        assert isinstance(result, PROpenResult)
        assert result.pr_url == "https://github.com/org/repo/pull/42"

        # File was rewritten
        assert (tmp_path / "Main.xaml").read_text() == "<Activity>patched</Activity>"

        # Expected command sequence
        cmds = [" ".join(c) for c in runner.calls]
        assert any(c.startswith("git checkout -b auto-heal/") for c in cmds)
        assert any(c.startswith("git add") for c in cmds)
        assert any(c.startswith("git commit") for c in cmds)
        assert any(c.startswith("gh pr create") for c in cmds)

    def test_pr_body_contains_evidence(self, tmp_path: Path) -> None:
        (tmp_path / "Main.xaml").write_text("<Activity>x</Activity>")
        runner = FakeRunner()
        opener = PROpener(repo_root=tmp_path, runner=runner)
        opener.open(
            bundle=_bundle(),
            candidate=_candidate(tmp_path),
            base_branch="main",
            staging_url="https://cloud.uipath.com/staging",
        )

        gh_cmd = next(c for c in runner.calls if c[:3] == ["gh", "pr", "create"])
        # --body-file path is the last arg after --body-file
        body_idx = gh_cmd.index("--body-file")
        body_path = Path(gh_cmd[body_idx + 1])
        body = body_path.read_text()
        assert "SelectorNotFoundException" in body
        assert "selector_repair" in body
        assert "staging-42" not in body  # staging URL may vary
        assert "https://cloud.uipath.com/staging" in body
        assert "submit-v2" in body

    def test_refuses_when_candidate_has_no_patches(self, tmp_path: Path) -> None:
        runner = FakeRunner()
        opener = PROpener(repo_root=tmp_path, runner=runner)
        candidate = FixCandidate(
            specialist="business_rule",
            confidence=0.9,
            diagnosis_category="business_rule_violation",
        )
        with pytest.raises(ValueError, match="no patches"):
            opener.open(
                bundle=_bundle(),
                candidate=candidate,
                base_branch="main",
                staging_url="",
            )
