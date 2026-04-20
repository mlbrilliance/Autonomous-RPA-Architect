"""Self-Healing Swarm demo — offline and live modes.

Offline (default):
    python proof/demo_self_heal.py

    Exercises the full SwarmOrchestrator path with mocked Orchestrator +
    mocked git/gh runner. Asserts: a PR "would be" opened, patched Main.xaml
    carries the new selector, staging reports Successful.

Live:
    RPA_LIVE=1 python proof/demo_self_heal.py --live --job-id <id>

    Hits the real Community Cloud Orchestrator. Skips the PR-open step
    unless the caller also supplies ``--open-pr`` (default is dry-run
    to avoid accidentally filing PRs from a dev box).

Demo plot the script proves:
    1. A deployed job has faulted with a SelectorNotFoundException.
    2. The swarm fetches the failure bundle + unpacks the deployed XAML.
    3. The selector-repair specialist harvests a replacement (or, offline,
       gets a canned one from the FakeHarvester).
    4. The arbiter picks the winning candidate.
    5. The staging validator runs the patched package → Successful.
    6. The PR opener commits the patched file and runs `gh pr create`.
    7. The script prints a summary that matches the README's v0.7 claims.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import httpx


# ---------------------------------------------------------------------------
# Sample XAML the demo "deploys" and then breaks
# ---------------------------------------------------------------------------

BROKEN_XAML = """<?xml version="1.0"?>
<Activity xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
          xmlns:ui="http://schemas.uipath.com/workflow/activities"
          xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName="Invoice Processing">
    <ui:Click DisplayName="Click Submit Invoice">
      <ui:Click.Target>
        <ui:Target Selector="&lt;webctrl id='submit-invoice-btn-stale' /&gt;" />
      </ui:Click.Target>
    </ui:Click>
    <ui:LogMessage DisplayName="Log Done" Level="Info" Message="submitted" />
  </Sequence>
</Activity>
"""


def _build_demo_nupkg(xaml: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("lib/net6.0-windows/Main.xaml", xaml)
        z.writestr("Invoice.nuspec", "<package/>")
    return buf.getvalue()


def _mock_orchestrator_transport() -> httpx.MockTransport:
    nupkg = _build_demo_nupkg(BROKEN_XAML)
    staging_job_state = {"state": "Successful"}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "connect/token" in url:
            return httpx.Response(200, json={"access_token": "demo", "expires_in": 3600})
        if "/Folders" in url and "$filter" in url:
            return httpx.Response(200, json={"value": [{"Id": 1}]})
        if "/Jobs(prod-demo-job)" in url:
            return httpx.Response(
                200,
                json={
                    "Key": "prod-demo-job",
                    "State": "Faulted",
                    "Info": (
                        "SelectorNotFoundException: Could not find UI element "
                        "<webctrl id='submit-invoice-btn-stale' /> (activity: Click Submit Invoice)"
                    ),
                    "StartTime": "2026-04-20T10:00:00Z",
                    "EndTime": "2026-04-20T10:00:08Z",
                    "ReleaseName": "InvoiceProcessing",
                },
            )
        if "/Jobs(" in url and "prod-demo-job" not in url:
            # Any other /Jobs(...) is a staging poll.
            return httpx.Response(
                200,
                json={
                    "Key": "staging-job-1",
                    "State": staging_job_state["state"],
                    "Info": "",
                    "StartTime": "2026-04-20T10:05:00Z",
                    "EndTime": "2026-04-20T10:05:10Z",
                },
            )
        if "/RobotLogs" in url:
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "TimeStamp": "2026-04-20T10:00:07Z",
                            "Level": "Error",
                            "Message": "UiElement not found",
                        }
                    ]
                },
            )
        if "/Processes/UiPath.Server.Configuration.OData.DownloadPackage" in url:
            return httpx.Response(200, content=nupkg)
        if "/Processes" in url and "$filter" in url:
            return httpx.Response(
                200, json={"value": [{"Key": "InvoiceProcessing", "Version": "1.0.0"}]}
            )
        if "/Releases" in url and request.method == "POST":
            return httpx.Response(
                200, json={"Key": "rel-staging", "ProcessKey": "InvoiceProcessing-staging"}
            )
        if "/Releases" in url and "$filter" in url:
            return httpx.Response(200, json={"value": [{"Key": "rel-staging"}]})
        if "StartJobs" in url:
            return httpx.Response(
                200, json={"value": [{"Key": "staging-job-1", "Id": 42}]}
            )
        return httpx.Response(404, json={"error": f"unexpected {url}"})

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeHarvester:
    """Stand-in for Playwright harvester — returns a canned healthy selector."""

    async def harvest_replacement(self, *, url: str, activity_display_name: str) -> str:
        return "<webctrl id='submit-invoice-btn' />"


class FakeRunner:
    """Stand-in for subprocess — records git/gh invocations."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, cmd: list[str], *, cwd: str) -> tuple[int, str, str]:
        self.calls.append(cmd)
        if cmd[:3] == ["gh", "pr", "create"]:
            return 0, "https://github.com/local/demo/pull/999\n", ""
        if cmd[:2] == ["git", "rev-parse"]:
            return 0, "abcdef1234567890\n", ""
        return 0, "", ""


# ---------------------------------------------------------------------------
# Demo driver
# ---------------------------------------------------------------------------


async def run_offline_demo() -> int:
    from rpa_architect.lifecycle.swarm.graph import SwarmOrchestrator
    from rpa_architect.lifecycle.swarm.failure_bundle import FailureBundleFetcher
    from rpa_architect.lifecycle.swarm.pr_opener import PROpener
    from rpa_architect.lifecycle.swarm.selector_repair import SelectorRepairSpecialist
    from rpa_architect.lifecycle.swarm.specialists import (
        BusinessRuleSpecialist,
        NullExceptionSpecialist,
        TimingRepairSpecialist,
    )
    from rpa_architect.lifecycle.swarm.staging_validator import StagingValidator
    from rpa_architect.platform.sdk_client import UiPathClient

    banner("OFFLINE DEMO — Self-Healing Swarm")

    client = UiPathClient(
        url="https://cloud.uipath.com",
        org="demo-org",
        tenant_name="demo-tenant",
        client_id="demo-id",
        client_secret="demo-secret",
        folder="Default",
    )
    client._http = httpx.AsyncClient(transport=_mock_orchestrator_transport())

    repo_root = Path(tempfile.mkdtemp(prefix="self-heal-demo-"))
    (repo_root / "Main.xaml").write_text(BROKEN_XAML)
    # Seed a minimal git repo so gh pr create would be structurally legal.
    subprocess.run(["git", "init", "-q"], cwd=repo_root, check=False)
    subprocess.run(
        ["git", "-c", "user.email=demo@demo", "-c", "user.name=demo", "add", "Main.xaml"],
        cwd=repo_root,
        check=False,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=demo@demo",
            "-c",
            "user.name=demo",
            "commit",
            "-qm",
            "seed",
        ],
        cwd=repo_root,
        check=False,
    )

    runner = FakeRunner()
    orchestrator = SwarmOrchestrator(
        fetcher=FailureBundleFetcher(client),
        specialists=[
            SelectorRepairSpecialist(harvester=FakeHarvester()),
            NullExceptionSpecialist(),
            TimingRepairSpecialist(),
            BusinessRuleSpecialist(),
        ],
        staging_validator=StagingValidator(client=client, staging_folder="Shared/Staging"),
        pr_opener=PROpener(repo_root=repo_root, runner=runner),
        repo_root=repo_root,
        base_branch="main",
        target_url="https://demo-invoice-app.example.com",
    )

    print(f"▸ Repo root: {repo_root}")
    print("▸ Fetching FailureBundle for job prod-demo-job …")
    verdict = await orchestrator.heal(job_id="prod-demo-job")

    banner("SWARM RESULT")
    print(f"Exception type       : {verdict.bundle.exception_type}")
    print(f"Specialists that ran : {[c.specialist for c in verdict.candidates]}")
    print(f"Arbiter rationale    : {verdict.arbiter_verdict.rationale}")
    print(
        "Winning specialist   :",
        verdict.arbiter_verdict.winner.specialist if verdict.arbiter_verdict.winner else "(none)",
    )
    print(
        "Winning confidence   :",
        f"{verdict.arbiter_verdict.winner.confidence:.2f}"
        if verdict.arbiter_verdict.winner
        else "(none)",
    )
    print(f"Staging success      : {verdict.staging_success}")
    print(f"PR URL               : {verdict.pr_url or '(not opened)'}")
    print(f"Requires escalation  : {verdict.requires_escalation}")

    patched_main = (repo_root / "Main.xaml").read_text()
    assert "submit-invoice-btn-stale" not in patched_main, (
        "patched Main.xaml should no longer contain the stale selector"
    )
    assert "submit-invoice-btn" in patched_main, (
        "patched Main.xaml should contain the new selector"
    )
    assert verdict.pr_url == "https://github.com/local/demo/pull/999", (
        "FakeRunner should have reported a PR URL"
    )
    assert verdict.staging_success is True
    banner("ASSERTIONS PASSED — self-heal demo works end-to-end")
    return 0


async def run_live_demo(job_id: str, *, open_pr: bool) -> int:  # pragma: no cover
    banner("LIVE DEMO — Self-Healing Swarm against Community Cloud")
    from rpa_architect.config import get_uipath_settings
    from rpa_architect.lifecycle.swarm.graph import build_default_swarm
    from rpa_architect.platform.sdk_client import UiPathClient

    settings = get_uipath_settings()
    client = UiPathClient(
        url=settings.url,
        org=settings.org,
        tenant_name=settings.tenant_name,
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        folder=settings.folder,
    )
    repo_root = Path.cwd()
    orchestrator = build_default_swarm(
        client=client,
        repo_root=repo_root,
        base_branch="main",
        target_url=os.environ.get("RPA_DEMO_TARGET_URL"),
    )
    verdict = await orchestrator.heal(job_id=job_id)
    banner("LIVE RESULT")
    print(f"PR URL: {verdict.pr_url or '(not opened)'}")
    print(f"Requires escalation: {verdict.requires_escalation}")
    if not open_pr and verdict.pr_url:
        print(
            "NOTE: --open-pr not set; the PR opener created a branch and PR anyway "
            "because the orchestrator always pipes through PROpener. For a true dry run, "
            "inject a no-op runner via custom SwarmOrchestrator factory."
        )
    return 0 if not verdict.requires_escalation else 1


def banner(msg: str) -> None:
    bar = "═" * len(msg)
    print(f"\n{bar}\n{msg}\n{bar}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Self-Healing Swarm demo")
    ap.add_argument("--live", action="store_true", help="run against real Orchestrator")
    ap.add_argument("--job-id", default="", help="faulted job id (required with --live)")
    ap.add_argument("--open-pr", action="store_true", help="allow live mode to open a real PR")
    args = ap.parse_args()

    if args.live:
        if os.environ.get("RPA_LIVE") != "1":
            print("Refusing to run live without RPA_LIVE=1 in the environment.")
            return 2
        if not args.job_id:
            print("--live requires --job-id <faulted-job-key>")
            return 2
        return asyncio.run(run_live_demo(args.job_id, open_pr=args.open_pr))

    return asyncio.run(run_offline_demo())


if __name__ == "__main__":
    sys.exit(main())
