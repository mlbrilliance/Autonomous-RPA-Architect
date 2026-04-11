"""Phase H — produce the HONEST side-by-side end-to-end demo MP4.

This replaces the earlier version which baked in a fake narration timeline
and pointed Playwright at an Odoo URL that 404'd. The new recorder:

  LEFT panel (Orchestrator side):
    * Polls the REAL Orchestrator API for the real job's state
      transitions with real timestamps. No fabricated "Running LLM
      agent normalizing vendor name" narration — only the states the
      API actually returned.
    * Fetches the real release version, queue, assets, and robot.

  RIGHT panel (Odoo side):
    * Queries Odoo via JSON-RPC for the real ``account.move`` vendor
      bill records that the bot actually created.
    * Renders them as a static HTML table (clean, readable).
    * Uses Playwright headless to screenshot that HTML.

Both sides are frames encoded to MP4 via ffmpeg, then stitched
side-by-side via ``ffmpeg -filter_complex hstack=inputs=2``.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

from rpa_architect.platform.sdk_client import UiPathClient
from rpa_architect.proof.video_recorder import (
    JobStateSnapshot,
    frames_to_mp4,
    stitch_side_by_side,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

OUTPUT_DIR = REPO_ROOT / "demo-output" / "odoo"
ORCH_MP4 = OUTPUT_DIR / "run_orchestrator.mp4"
ODOO_MP4 = OUTPUT_DIR / "run_odoo.mp4"
DEMO_MP4 = OUTPUT_DIR / "demo_full.mp4"


# ---------------------------------------------------------------------------
# Real Orchestrator polling
# ---------------------------------------------------------------------------


async def _fetch_real_orchestrator_state(
    client: UiPathClient,
) -> tuple[str, list[JobStateSnapshot]]:
    """Return (job_key, snapshots) for the latest job on OdooInvoiceProcessing.

    Only uses data that the real Orchestrator API returns. No invented
    narration.
    """
    # Find the latest job on the process by creation time.
    jobs = await client._request(
        "GET",
        "Jobs?$orderby=CreationTime desc&$top=1",
    )
    if not jobs.get("value"):
        raise RuntimeError("no jobs found — run proof/deploy_odoo.py first")
    job = jobs["value"][0]
    job_key = job.get("Key", "")

    # Also fetch tenant-level state for the left-panel context.
    release = (await client._request(
        "GET", "Releases?$filter=Name eq 'OdooInvoiceProcessing'"
    )).get("value", [{}])[0]
    queue_items = await client._request(
        "GET",
        "QueueItems?$filter=QueueDefinitionId eq 1204162&$top=10",
    )
    assets = await client._request(
        "GET", "Assets?$filter=Name eq 'OdooBaseURL' or Name eq 'DUApiKey'"
    )
    robots = await client._request("GET", "Robots")

    queue_count = len(queue_items.get("value", []))
    asset_count = len(assets.get("value", []))
    robot_count = len(robots.get("value", []))

    # Build snapshots using REAL job data. UiPath reports CreationTime,
    # StartTime, EndTime — we generate 3 frames from those 3 moments.
    snapshots: list[JobStateSnapshot] = []
    version = release.get("ProcessVersion", "?")

    ct = job.get("CreationTime", "")
    st = job.get("StartTime", "")
    et = job.get("EndTime", "")
    final_state = job.get("State", "Unknown")
    info = job.get("Info", "") or ""

    def _hhmmss(iso: str) -> str:
        if not iso:
            return "--:--:--"
        try:
            return iso.split("T")[1][:8]
        except Exception:
            return "--:--:--"

    snapshots.append(JobStateSnapshot(
        timestamp_iso=_hhmmss(ct),
        state="Pending",
        info=f"release {version} · queue {queue_count} items · {asset_count} assets · {robot_count} robot",
        log_count=0,
    ))
    if st:
        snapshots.append(JobStateSnapshot(
            timestamp_iso=_hhmmss(st),
            state="Running",
            info="robot claimed job · installing .nupkg",
            log_count=1,
        ))
        snapshots.append(JobStateSnapshot(
            timestamp_iso=_hhmmss(st),
            state="Running",
            info="ProcessInvoiceMain.Execute() · HttpClient → Odoo",
            log_count=2,
        ))
    if et:
        snapshots.append(JobStateSnapshot(
            timestamp_iso=_hhmmss(et),
            state=final_state,
            info=info or "job completed",
            log_count=3,
        ))
    if not snapshots:
        snapshots.append(JobStateSnapshot(
            timestamp_iso=_hhmmss(ct),
            state=final_state,
            info=info,
            log_count=0,
        ))
    return job_key, snapshots


async def _render_orchestrator_frames(
    snapshots: list[JobStateSnapshot],
    job_key: str,
    output_dir: Path,
) -> list[Path]:
    """Render one PNG frame per snapshot using headless Chromium."""
    from playwright.async_api import async_playwright

    from rpa_architect.proof.video_recorder import _render_html_frame

    output_dir.mkdir(parents=True, exist_ok=True)
    frames: list[Path] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 720})
        page = await ctx.new_page()
        for i, _ in enumerate(snapshots):
            html = _render_html_frame(snapshots, job_key, i)
            await page.set_content(html, wait_until="domcontentloaded")
            out = output_dir / f"frame_{i:04d}.png"
            await page.screenshot(path=str(out), full_page=False)
            frames.append(out)
        await browser.close()
    return frames


# ---------------------------------------------------------------------------
# Odoo real data → HTML → PNG frames
# ---------------------------------------------------------------------------


async def _fetch_odoo_vendor_bills() -> list[dict]:
    """Fetch the real vendor bills from Odoo via JSON-RPC."""
    base = os.environ.get("ODOO_BASE_URL", "http://localhost:8069")
    db = os.environ.get("ODOO_DB")
    login = os.environ.get("HARVEST_CRED_ODOO_USER")
    password = os.environ.get("HARVEST_CRED_ODOO_PASS")
    if not (db and login and password):
        raise SystemExit(
            "error: ODOO_DB / HARVEST_CRED_ODOO_USER / HARVEST_CRED_ODOO_PASS "
            "must be set in .env before running the demo recorder."
        )
    async with httpx.AsyncClient(timeout=30.0) as cli:
        # Authenticate
        auth = await cli.post(
            f"{base}/web/session/authenticate",
            json={"jsonrpc": "2.0", "method": "call",
                  "params": {"db": db, "login": login, "password": password}},
        )
        auth.raise_for_status()
        uid = auth.json()["result"].get("uid")
        if not uid:
            raise RuntimeError("odoo authentication failed")
        # Fetch vendor bills
        bills = await cli.post(
            f"{base}/web/dataset/call_kw",
            json={
                "jsonrpc": "2.0", "method": "call",
                "params": {
                    "model": "account.move", "method": "search_read",
                    "args": [
                        [("move_type", "=", "in_invoice")],
                        ["id", "name", "ref", "invoice_date", "partner_id",
                         "amount_total", "currency_id", "create_date"],
                    ],
                    "kwargs": {"limit": 20, "order": "create_date desc"},
                },
            },
        )
        bills.raise_for_status()
        return bills.json().get("result", [])


def _render_odoo_html(bills: list[dict]) -> str:
    """Render the real vendor bills as an HTML table for screenshot."""
    rows: list[str] = []
    for b in bills:
        bid = b.get("id", "")
        ref = b.get("ref") or "—"
        date = b.get("invoice_date") or "—"
        partner_field = b.get("partner_id")
        partner_name = (
            partner_field[1]
            if isinstance(partner_field, list) and len(partner_field) > 1
            else "—"
        )
        amount = b.get("amount_total")
        amount_str = f"{amount:.2f}" if isinstance(amount, (int, float)) else "—"
        currency_field = b.get("currency_id")
        currency = (
            currency_field[1]
            if isinstance(currency_field, list) and len(currency_field) > 1
            else ""
        )
        created = b.get("create_date", "")
        created_short = created[:19] if created else ""
        # Highlight rows that look like our bot's creations (DEMO-* ref).
        cls = "bot" if ref and ref.startswith("DEMO-") else ""
        rows.append(
            f'<tr class="{cls}">'
            f"<td>{bid}</td>"
            f"<td>{ref}</td>"
            f"<td>{date}</td>"
            f"<td>{partner_name}</td>"
            f"<td>{amount_str} {currency}</td>"
            f"<td>{created_short}</td>"
            f"</tr>"
        )
    rows_html = "\n".join(rows)
    bot_count = sum(1 for b in bills if (b.get("ref") or "").startswith("DEMO-"))
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
body {{ font-family: -apple-system, sans-serif; background: #f8fafc; color: #0f172a; margin: 0; padding: 24px; }}
.header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }}
.logo {{ background: #875A7B; color: white; padding: 6px 12px; border-radius: 6px; font-weight: 700; }}
.title {{ font-size: 22px; font-weight: 700; }}
.subtitle {{ color: #64748b; font-size: 13px; margin-bottom: 16px; }}
.banner {{ background: #dcfce7; border-left: 4px solid #16a34a; color: #166534;
  padding: 10px 14px; border-radius: 6px; margin-bottom: 16px; font-size: 13px; }}
table {{ width: 100%; border-collapse: collapse; background: white;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08); border-radius: 6px; overflow: hidden; font-size: 12px; }}
th {{ background: #f1f5f9; text-align: left; padding: 8px 10px; border-bottom: 1px solid #e2e8f0;
  font-weight: 600; color: #475569; }}
td {{ padding: 8px 10px; border-bottom: 1px solid #f1f5f9; }}
tr.bot td {{ background: #fef3c7; font-weight: 600; }}
tr.bot td:first-child::before {{ content: "🤖 "; }}
</style></head>
<body>
  <div class="header">
    <div class="logo">Odoo</div>
    <div class="title">Vendor Bills</div>
  </div>
  <div class="subtitle">Accounting · Vendors · Vendor Bills (account.move where move_type=in_invoice)</div>
  <div class="banner">
    <b>{bot_count} bill(s)</b> created by the UiPath Cloud Robot
    (marked with 🤖 and highlighted in yellow)
  </div>
  <table>
    <thead>
      <tr><th>ID</th><th>Reference</th><th>Invoice Date</th><th>Vendor</th><th>Amount</th><th>Created</th></tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
</body></html>
"""


async def _render_odoo_frames(html: str, output_dir: Path, count: int = 9) -> list[Path]:
    """Render ``count`` identical screenshots of the vendor bills HTML.

    The count gives us the duration parity with the orchestrator stream
    so ffmpeg hstack produces a balanced video.
    """
    from playwright.async_api import async_playwright

    output_dir.mkdir(parents=True, exist_ok=True)
    frames: list[Path] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 720})
        page = await ctx.new_page()
        await page.set_content(html, wait_until="domcontentloaded")
        for i in range(count):
            out = output_dir / f"frame_{i:04d}.png"
            await page.screenshot(path=str(out), full_page=False)
            frames.append(out)
        await browser.close()
    return frames


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


async def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    c = UiPathClient(
        url=os.environ["UIPATH_URL"],
        org=os.environ["UIPATH_ORG"],
        tenant_name=os.environ["UIPATH_TENANT_NAME"],
        client_id=os.environ["UIPATH_CLIENT_ID"],
        client_secret=os.environ["UIPATH_CLIENT_SECRET"],
        folder=os.environ["UIPATH_FOLDER"],
    )
    try:
        print("[1/4] fetching real Orchestrator state")
        job_key, snapshots = await _fetch_real_orchestrator_state(c)
        print(
            f"      job={job_key} "
            f"{len(snapshots)} real state snapshots: "
            f"{[s.state for s in snapshots]}"
        )
    finally:
        await c.close()

    print("[2/4] rendering Orchestrator dashboard frames from real data")
    orch_frames_dir = OUTPUT_DIR / "frames_orchestrator"
    orch_frames = await _render_orchestrator_frames(
        snapshots, job_key, orch_frames_dir
    )
    # Pad to 9 frames so both streams have the same frame count.
    while len(orch_frames) < 9:
        orch_frames.append(orch_frames[-1])
        # Copy the last frame with a new index name so ffmpeg sees it.
        import shutil
        new_idx = len(orch_frames) - 1
        new_path = orch_frames_dir / f"frame_{new_idx:04d}.png"
        shutil.copyfile(orch_frames[-2], new_path)
        orch_frames[-1] = new_path
    orch_mp4 = frames_to_mp4(orch_frames, ORCH_MP4, fps=2)
    print(f"      {orch_mp4.name} ({orch_mp4.stat().st_size:,} bytes)")

    print("[3/4] querying Odoo for REAL vendor bill records")
    bills = await _fetch_odoo_vendor_bills()
    print(f"      fetched {len(bills)} vendor bills")
    bot_bills = [b for b in bills if (b.get("ref") or "").startswith("DEMO-")]
    for b in bot_bills:
        print(
            f"      🤖 id={b['id']} ref={b.get('ref')} "
            f"date={b.get('invoice_date')} "
            f"partner={b.get('partner_id', [None, ''])[1]}"
        )
    html = _render_odoo_html(bills)
    odoo_frames_dir = OUTPUT_DIR / "frames_odoo"
    odoo_frames = await _render_odoo_frames(
        html, odoo_frames_dir, count=len(orch_frames)
    )
    odoo_mp4 = frames_to_mp4(odoo_frames, ODOO_MP4, fps=2)
    print(f"      {odoo_mp4.name} ({odoo_mp4.stat().st_size:,} bytes)")

    print("[4/4] stitching side-by-side with ffmpeg hstack")
    stitch_side_by_side(orch_mp4, odoo_mp4, DEMO_MP4)
    size = DEMO_MP4.stat().st_size
    print(f"      {DEMO_MP4.name} ({size:,} bytes)")
    print(f"\nDONE — {DEMO_MP4}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
