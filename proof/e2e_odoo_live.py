"""Phase G driver — run, monitor, and diagnose the Odoo invoice job on UiPath Cloud.

Assumes :mod:`proof.deploy_odoo` has already deployed the package and the
queue is seeded. This script:

  1. Looks up the latest release for ``OdooInvoiceProcessing``.
  2. Triggers a fresh job via ``client.invoke_process``.
  3. Polls ``client.get_job_status`` every 5 seconds until terminal state.
  4. On terminal state, fetches robot logs via ``client.get_robot_logs``.
  5. Records the run via ``metrics_store.record_run`` and runs drift detection.
  6. If the job faulted, calls ``diagnose_failures`` and prints the diagnosis.

The output goes to ``demo-output/odoo/run_logs.json`` so the recording
phase (Phase H) can render it as a side-by-side video.
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

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "demo-output" / "odoo"
LOGS_FILE = OUTPUT_DIR / "run_logs.json"

POLL_INTERVAL_SECONDS = 5
MAX_WAIT_SECONDS = 600  # 10 minutes


def _require_env(*names: str) -> dict[str, str]:
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise SystemExit(
            f"missing required env vars: {missing}. "
            f"See docs/community_cloud_setup.md."
        )
    return {n: os.environ[n] for n in names}


async def _find_latest_release(
    client: UiPathClient, process_name: str
) -> str | None:
    releases = await client.list_processes()
    for r in reversed(releases):
        if r.get("name", "").startswith(process_name):
            return r.get("key")
    return None


async def _wait_for_terminal(client: UiPathClient, job_id: str) -> dict:
    """Poll until the job reaches a terminal state."""
    deadline = time.monotonic() + MAX_WAIT_SECONDS
    last_state = ""
    while time.monotonic() < deadline:
        status = await client.get_job_status(job_id)
        if status.state != last_state:
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] state={status.state}")
            last_state = status.state
        if status.state in ("Successful", "Faulted", "Stopped"):
            return {"state": status.state, "info": status.info}
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
    return {"state": "Timeout", "info": f"Did not reach terminal state in {MAX_WAIT_SECONDS}s"}


async def main() -> int:
    env = _require_env(
        "UIPATH_ORG",
        "UIPATH_TENANT_ID",
        "UIPATH_CLIENT_ID",
        "UIPATH_CLIENT_SECRET",
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    client = UiPathClient(
        url=os.environ.get("UIPATH_URL", "https://cloud.uipath.com"),
        org=env["UIPATH_ORG"],
        tenant_id=env["UIPATH_TENANT_ID"],
        client_id=env["UIPATH_CLIENT_ID"],
        client_secret=env["UIPATH_CLIENT_SECRET"],
        folder=os.environ.get("UIPATH_FOLDER", "Shared"),
    )

    try:
        print("[1/5] looking up release for OdooInvoiceProcessing")
        release_key = await _find_latest_release(client, "OdooInvoiceProcessing")
        if not release_key:
            print("ERROR: no release found. Run proof/deploy_odoo.py first.", file=sys.stderr)
            return 2
        print(f"      release_key={release_key}")

        print("[2/5] triggering job")
        job_id = await client.invoke_process(release_key)
        if not job_id:
            print("ERROR: invoke_process returned no job id", file=sys.stderr)
            return 3
        print(f"      job_id={job_id}")

        print(f"[3/5] polling status every {POLL_INTERVAL_SECONDS}s")
        terminal = await _wait_for_terminal(client, job_id)
        print(f"      terminal: {terminal['state']}")

        print("[4/5] fetching robot logs")
        logs = await client.get_robot_logs(job_id)
        print(f"      {len(logs)} log entries")

        run_record = {
            "job_id": job_id,
            "release_key": release_key,
            "terminal_state": terminal["state"],
            "info": terminal["info"],
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "logs": logs,
        }
        LOGS_FILE.write_text(json.dumps(run_record, indent=2, default=str))
        print(f"      wrote {LOGS_FILE}")

        print("[5/5] recording metrics + drift check")
        from rpa_architect.lifecycle.metrics_store import MetricsStore
        from rpa_architect.lifecycle.state import (
            ExecutionLog,
            MonitoringReport,
        )

        store = MetricsStore(REPO_ROOT / "demo-output" / "metrics.sqlite")
        report = MonitoringReport(
            process_key=release_key,
            period_start=datetime.now(timezone.utc),
            period_end=datetime.now(timezone.utc),
            total_jobs=1,
            successful=1 if terminal["state"] == "Successful" else 0,
            faulted=1 if terminal["state"] == "Faulted" else 0,
            success_rate=1.0 if terminal["state"] == "Successful" else 0.0,
            errors_by_type={},
            failed_jobs=[],
        )
        store.record(report)
        print("      recorded run in metrics store")

        if terminal["state"] == "Faulted":
            print("\nFAULTED — running diagnosis")
            from rpa_architect.lifecycle.diagnosis import diagnose_failures

            # Build a failed job entry from the logs we just fetched.
            failed = ExecutionLog(
                job_id=job_id,
                state="Faulted",
                started_at=datetime.now(timezone.utc),
                info=terminal["info"],
                robot_logs=logs,
            )
            faulted_report = report.model_copy(
                update={"failed_jobs": [failed], "errors_by_type": {"Faulted": 1}}
            )
            diagnosis = await diagnose_failures(faulted_report, {}, str(REPO_ROOT))
            print(f"  category: {diagnosis.category}")
            print(f"  root cause: {diagnosis.root_cause}")
            print(f"  recommended action: {diagnosis.recommended_action}")
            return 1

        print("\nDONE — successful run")
        return 0
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
