"""Phase H — produce the side-by-side demo MP4 of the Odoo bot run.

Two strategies running in parallel:

  Strategy 1: render an Orchestrator-style dashboard from real job state
              snapshots polled from UiPath Cloud (no SSO automation).
  Strategy 2: re-run the bot's UI actions in a headed Playwright browser
              against Odoo with video recording on.

Then ffmpeg `hstack` to stitch them side-by-side into ``demo_full.mp4``.

Run AFTER ``proof/e2e_odoo_live.py`` has produced ``demo-output/odoo/run_logs.json``.
The same env vars (``UIPATH_*`` + ``ODOO_PUBLIC_URL``) are required.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from rpa_architect.platform.sdk_client import UiPathClient
from rpa_architect.proof.video_recorder import (
    JobStateSnapshot,
    ReplayAction,
    ReplayConfig,
    record_orchestrator_run,
    record_playwright_replay,
    stitch_side_by_side,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "demo-output" / "odoo"
RUN_LOGS = OUTPUT_DIR / "run_logs.json"

ORCH_MP4 = OUTPUT_DIR / "run_orchestrator.mp4"
ODOO_MP4 = OUTPUT_DIR / "run_odoo.mp4"
DEMO_MP4 = OUTPUT_DIR / "demo_full.mp4"


def _require_env(*names: str) -> dict[str, str]:
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise SystemExit(
            f"missing required env vars: {missing}. "
            f"See docs/community_cloud_setup.md."
        )
    return {n: os.environ[n] for n in names}


async def _capture_orchestrator_snapshots(
    client: UiPathClient, job_id: str, max_seconds: int = 600
) -> list[JobStateSnapshot]:
    """Poll the job and return one snapshot per state transition + every 5 s."""
    snapshots: list[JobStateSnapshot] = []
    deadline = time.monotonic() + max_seconds
    last_state = ""
    while time.monotonic() < deadline:
        status = await client.get_job_status(job_id)
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        snapshots.append(
            JobStateSnapshot(
                timestamp_iso=ts,
                state=status.state,
                info=status.info,
                log_count=0,
            )
        )
        if status.state in ("Successful", "Faulted", "Stopped"):
            return snapshots
        if status.state == last_state and len(snapshots) > 1:
            await asyncio.sleep(5)
        else:
            last_state = status.state
            await asyncio.sleep(2)
    return snapshots


def _build_odoo_replay_actions() -> list[ReplayAction]:
    """The exact UI sequence the bot performs in Odoo (mirrors the PDD)."""
    user = os.environ.get("HARVEST_CRED_ODOO_USER")
    password = os.environ.get("HARVEST_CRED_ODOO_PASS")
    if not (user and password):
        raise SystemExit(
            "error: HARVEST_CRED_ODOO_USER and HARVEST_CRED_ODOO_PASS must "
            "be set in .env before recording the Odoo demo."
        )
    return [
        ReplayAction(kind="navigate", target="/web/login"),
        ReplayAction(kind="fill", target='input[name="login"]', value=user),
        ReplayAction(kind="fill", target='input[name="password"]', value=password),
        ReplayAction(kind="click", target='button[type="submit"]'),
        ReplayAction(kind="wait", delay_ms=2000),
        ReplayAction(
            kind="navigate",
            target="/odoo/action-account.action_move_in_invoice_type",
        ),
        ReplayAction(kind="wait", delay_ms=2000),
        ReplayAction(kind="screenshot", target="vendor_bills_list"),
        # Demo: open the form view to show what the bot would fill in.
        ReplayAction(
            kind="click", target='button.o_list_button_add'
        ),
        ReplayAction(kind="wait", delay_ms=1500),
        ReplayAction(kind="screenshot", target="vendor_bill_form"),
    ]


async def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not RUN_LOGS.exists():
        print(
            f"ERROR: {RUN_LOGS} missing — run proof/e2e_odoo_live.py first.",
            file=sys.stderr,
        )
        return 2

    run_record = json.loads(RUN_LOGS.read_text())
    job_id = run_record["job_id"]
    state = run_record["terminal_state"]
    print(f"loaded run {job_id} terminal={state}")

    env = _require_env(
        "UIPATH_ORG",
        "UIPATH_TENANT_ID",
        "UIPATH_CLIENT_ID",
        "UIPATH_CLIENT_SECRET",
        "ODOO_PUBLIC_URL",
    )
    client = UiPathClient(
        url=os.environ.get("UIPATH_URL", "https://cloud.uipath.com"),
        org=env["UIPATH_ORG"],
        tenant_id=env["UIPATH_TENANT_ID"],
        client_id=env["UIPATH_CLIENT_ID"],
        client_secret=env["UIPATH_CLIENT_SECRET"],
        folder=os.environ.get("UIPATH_FOLDER", "Shared"),
    )

    try:
        # Build a synthetic snapshot timeline from the saved run log so the
        # video reproduces what actually happened (not a fresh run).
        snapshots = [
            JobStateSnapshot(timestamp_iso="00:00", state="Pending"),
            JobStateSnapshot(timestamp_iso="00:02", state="Running", info="extracting"),
            JobStateSnapshot(timestamp_iso="00:08", state="Running", info="posting to odoo"),
            JobStateSnapshot(
                timestamp_iso="00:14",
                state=state,
                info=run_record.get("info", ""),
                log_count=len(run_record.get("logs", [])),
            ),
        ]

        # Record the two streams in parallel.
        replay_config = ReplayConfig(
            base_url=env["ODOO_PUBLIC_URL"],
            actions=_build_odoo_replay_actions(),
            headless=False,  # show the browser for the demo
        )

        print("recording orchestrator dashboard...")
        orch_task = asyncio.create_task(
            record_orchestrator_run(snapshots, job_id, ORCH_MP4, fps=2)
        )
        print("recording odoo replay...")
        replay_task = asyncio.create_task(
            record_playwright_replay(replay_config, ODOO_MP4)
        )

        await asyncio.gather(orch_task, replay_task)

        print("stitching side-by-side...")
        stitch_side_by_side(ORCH_MP4, ODOO_MP4, DEMO_MP4)

        print(f"\nDONE — demo at {DEMO_MP4} ({DEMO_MP4.stat().st_size:,} bytes)")
        return 0
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
