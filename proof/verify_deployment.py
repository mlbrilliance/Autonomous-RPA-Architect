"""Phase G verification — fetch the live Orchestrator state after deployment.

Captures a JSON snapshot of every artifact the deploy_odoo.py script
created on UiPath Community Cloud (packages, release, queue items,
assets, robot) and writes it to ``demo-output/odoo/verification.json``.
Phase H consumes this to render the Orchestrator dashboard side of
the demo video.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from rpa_architect.platform.sdk_client import UiPathClient

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

OUTPUT = REPO_ROOT / "demo-output" / "odoo" / "verification.json"
PROCESS_NAME = "OdooInvoiceProcessing"


async def main() -> int:
    c = UiPathClient(
        url=os.environ["UIPATH_URL"],
        org=os.environ["UIPATH_ORG"],
        tenant_name=os.environ["UIPATH_TENANT_NAME"],
        client_id=os.environ["UIPATH_CLIENT_ID"],
        client_secret=os.environ["UIPATH_CLIENT_SECRET"],
        folder=os.environ["UIPATH_FOLDER"],
    )
    snapshot: dict = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "org": os.environ["UIPATH_ORG"],
        "tenant": os.environ["UIPATH_TENANT_NAME"],
        "folder": os.environ["UIPATH_FOLDER"],
    }
    try:
        # 1. Packages
        print("[1/6] packages")
        packages = await c._request(
            "GET",
            f"Processes?$filter=startswith(Id,'{PROCESS_NAME}')",
        )
        snapshot["packages"] = [
            {
                "id": p.get("Id"),
                "version": p.get("Version"),
                "title": p.get("Title"),
            }
            for p in packages.get("value", [])
        ]
        print(f"      {len(snapshot['packages'])} package versions")

        # 2. Releases
        print("[2/6] releases")
        releases = await c._request(
            "GET", f"Releases?$filter=Name eq '{PROCESS_NAME}'"
        )
        snapshot["releases"] = [
            {
                "id": r.get("Id"),
                "key": r.get("Key"),
                "name": r.get("Name"),
                "processKey": r.get("ProcessKey"),
                "processVersion": r.get("ProcessVersion"),
                "requiresUserInteraction": r.get("RequiresUserInteraction"),
            }
            for r in releases.get("value", [])
        ]
        print(f"      {len(snapshot['releases'])} release(s)")

        # 3. Queue
        print("[3/6] queue definition")
        queues = await c._request(
            "GET", "QueueDefinitions?$filter=Name eq 'OdooInvoices'"
        )
        q = queues.get("value", [{}])[0]
        snapshot["queue"] = {
            "id": q.get("Id"),
            "name": q.get("Name"),
            "description": q.get("Description"),
        }
        print(f"      id={snapshot['queue'].get('id')}")

        # 4. Queue items
        print("[4/6] queue items")
        items = await c._request(
            "GET",
            "QueueItems?$filter=QueueDefinitionId eq "
            f"{snapshot['queue']['id']}&$top=10",
        )
        snapshot["queue_items"] = [
            {
                "id": i.get("Id"),
                "reference": i.get("Reference"),
                "status": i.get("Status"),
                "priority": i.get("Priority"),
                "specificContent": i.get("SpecificContent"),
            }
            for i in items.get("value", [])
        ]
        print(f"      {len(snapshot['queue_items'])} items")

        # 5. Assets
        print("[5/6] assets")
        assets = await c._request(
            "GET",
            "Assets?$filter=Name eq 'OdooBaseURL' or Name eq 'DUApiKey'",
        )
        snapshot["assets"] = [
            {
                "id": a.get("Id"),
                "name": a.get("Name"),
                "valueType": a.get("ValueType"),
                "valueScope": a.get("ValueScope"),
                # Never capture the actual value — just proof of existence.
            }
            for a in assets.get("value", [])
        ]
        print(f"      {len(snapshot['assets'])} asset(s)")

        # 6. Robots
        print("[6/6] robots")
        robots = await c._request("GET", "Robots")
        snapshot["robots"] = [
            {
                "id": r.get("Id"),
                "name": r.get("Name"),
                "type": r.get("Type"),
            }
            for r in robots.get("value", [])
        ]
        print(f"      {len(snapshot['robots'])} robot(s)")

        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(snapshot, indent=2))
        print(f"\nwrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes)")

        # Human-readable summary
        print("\n=== DEPLOYMENT PROOF ===")
        print(f"  packages:    {len(snapshot['packages'])} version(s)")
        print(f"  releases:    {len(snapshot['releases'])}")
        print(f"  queue:       {snapshot['queue'].get('name')} (id={snapshot['queue'].get('id')})")
        print(f"  queue items: {len(snapshot['queue_items'])}")
        print(f"  assets:      {len(snapshot['assets'])}")
        print(f"  robots:      {len(snapshot['robots'])}")
        return 0
    finally:
        await c.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
